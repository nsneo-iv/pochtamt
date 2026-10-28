# Глобальное правило (выполняется до пользовательских): письма, отмеченные Rspamd как спам, — в Junk
require ["fileinto", "mailbox"];
if header :contains "X-Spam" "Yes" {
    fileinto :create "Junk";
    stop;
}
