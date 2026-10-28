# свои сети: от них не проверяем SPF/greylist, подписываем DKIM
local_addrs = "127.0.0.0/8, @LAN_NETS_COMMA@";
dns {
  nameserver = ["127.0.0.1:53"];
}
