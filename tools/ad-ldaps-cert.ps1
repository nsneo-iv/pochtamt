<#
.SYNOPSIS
  Включить LDAPS (636/3269) на контроллере домена: самоподписанный сертификат сервера в хранилище компьютера.

.DESCRIPTION
  Типичная картина: порт 636 открыт, но TLS не поднимается — нет сертификата с EKU «Проверка подлинности сервера»
  (центра сертификации в домене нет). Скрипт:
    1. если подходящий действующий сертификат уже есть — ничего не создаёт, только печатает его;
    2. иначе создаёт самоподписанный RSA-2048 / SHA-256 на 5 лет с SAN = FQDN DC, имя хоста и имя леса;
    3. кладёт открытую копию в доверенные корни DC (иначе Schannel её не берёт);
    4. просит AD DS подхватить сертификат без перезапуска службы (renewServerCertificate);
    5. проверяет TLS на localhost:636 и печатает открытую часть сертификата (PEM) — её кладут на клиентов
       как доверенный (почтовый сервер Pochtamt: install/certs/ad-ca.pem, ключ AD_CA_CERT в install/.env).
  Закрытый ключ не экспортируется. Откат: удалить сертификат из Cert:\LocalMachine\My по отпечатку —
  LDAPS пропадёт, LDAP на 389/3268 не затрагивается.
  Запуск на DC от администратора (PowerShell 5.1+): .\ad-ldaps-cert.ps1  [-Years 5]  [-WhatIf]
#>
[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [int] $Years = 5
)
$ErrorActionPreference = 'Stop'

$fqdn = ([System.Net.Dns]::GetHostEntry('localhost')).HostName
if ($fqdn -notmatch '\.') { $fqdn = "$env:COMPUTERNAME.$env:USERDNSDOMAIN".ToLower() }
$forest = $env:USERDNSDOMAIN.ToLower()
Write-Host "DC: $fqdn"

function Test-ServerAuthCert($c) {
    $c.HasPrivateKey -and $c.NotAfter -gt (Get-Date).AddDays(30) -and
    ($c.EnhancedKeyUsageList.ObjectId -contains '1.3.6.1.5.5.7.3.1') -and
    ($c.DnsNameList.Unicode -contains $fqdn)
}

$cert = Get-ChildItem Cert:\LocalMachine\My | Where-Object { Test-ServerAuthCert $_ } |
    Sort-Object NotAfter -Descending | Select-Object -First 1

if ($cert) {
    Write-Host "Подходящий сертификат уже есть: $($cert.Thumbprint), до $($cert.NotAfter)"
} elseif ($PSCmdlet.ShouldProcess($fqdn, 'создать самоподписанный сертификат для LDAPS')) {
    $names = @($fqdn, $env:COMPUTERNAME.ToLower(), $forest) | Select-Object -Unique
    $cert = New-SelfSignedCertificate `
        -Subject "CN=$fqdn" `
        -DnsName $names `
        -KeyAlgorithm RSA -KeyLength 2048 -HashAlgorithm SHA256 `
        -KeyExportPolicy NonExportable `
        -KeyUsage DigitalSignature, KeyEncipherment `
        -TextExtension @('2.5.29.37={text}1.3.6.1.5.5.7.3.1') `
        -Provider 'Microsoft RSA SChannel Cryptographic Provider' `
        -CertStoreLocation Cert:\LocalMachine\My `
        -NotAfter (Get-Date).AddYears($Years)
    Write-Host "Создан сертификат: $($cert.Thumbprint), до $($cert.NotAfter)"
} else {
    return
}

# Schannel не берёт самоподписанный сертификат как «учётные данные по умолчанию» (событие 36886), пока он не
# в доверенных корнях самого DC. В корни кладётся только открытая копия этого же сертификата.
if (-not (Get-ChildItem Cert:\LocalMachine\Root | Where-Object { $_.Thumbprint -eq $cert.Thumbprint })) {
    $cer = Join-Path $env:TEMP 'dc-ldaps.cer'
    Export-Certificate -Cert $cert -FilePath $cer -Force | Out-Null
    Import-Certificate -FilePath $cer -CertStoreLocation Cert:\LocalMachine\Root | Out-Null
    Remove-Item $cer -Force
    Write-Host 'Открытая копия добавлена в Trusted Root этого DC'
}

# AD DS перечитывает хранилище сам; renewServerCertificate ускоряет (может быть недоступен для сетевой сессии)
try {
    $root = [ADSI]'LDAP://localhost/rootDSE'
    $root.Put('renewServerCertificate', 1)
    $root.SetInfo()
    Write-Host 'AD DS попросили перечитать сертификат'
} catch {
    Write-Warning "renewServerCertificate не выполнен: $($_.Exception.Message) (подхватится автоматически)"
}

# проверка: рукопожатие TLS на localhost:636 и какой сертификат отдаётся
Start-Sleep -Seconds 3
foreach ($port in 636, 3269) {
    try {
        $tcp = New-Object Net.Sockets.TcpClient('localhost', $port)
        $ssl = New-Object Net.Security.SslStream($tcp.GetStream(), $false, { $true })
        $ssl.AuthenticateAsClient($fqdn)
        $served = New-Object Security.Cryptography.X509Certificates.X509Certificate2 $ssl.RemoteCertificate
        Write-Host ("порт {0}: TLS OK ({1}), сертификат {2}" -f $port, $ssl.SslProtocol, $served.Thumbprint)
        $ssl.Dispose(); $tcp.Dispose()
    } catch {
        Write-Warning ("порт {0}: TLS не поднялся: {1}" -f $port, $_.Exception.Message)
    }
}

$b64 = [Convert]::ToBase64String($cert.RawData, 'InsertLineBreaks')
Write-Host '-----BEGIN CERTIFICATE-----'
Write-Host $b64
Write-Host '-----END CERTIFICATE-----'
