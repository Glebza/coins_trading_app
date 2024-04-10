import telebot, os

bot = telebot.TeleBot(os.environ['TELEGRAM_TOKEN'])
groups_id = [-575029157]
@bot.message_handler(content_types=['text'])
def get_text_messages(message):
    print(message)
    if message.text == "/start":
        #groups_id.append(message.chat.id)
        bot.send_message(message.chat.id, 'хуярт')
    print(groups_id)


def send_message(message):
    for group_id in groups_id:
        bot.send_message(group_id, message)

if __name__ == '__main__':
    bot.polling(none_stop=True, interval=0)