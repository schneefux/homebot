#!/usr/bin/python3
# generic libraries
import random
import string
import os
import requests
import sched
import time

# installable libraries
import telegram
import homeassistant.remote as remote

# user configuration
IP = "192.168.1.29"
PASSW = ""
TOKEN = ""

# GUI constants
KEYBOARD_WIDTH = 4
ACL_FILE = os.path.dirname(os.path.realpath(__file__)) +\
    "/trusted_users"

# constants
MENU_MEOW = "/meow"
MENU_DIE = "/shutdown"
MENU_STATES = "/see_states"
MENU_STATES_SUB = "/state"
MENU_SWITCHES = "/see_switches"
MENU_SWITCH_SUB = "/switch"
COMMAND_SWITCH = "/set"
COMMAND_STATE = "/show"
COMMAND_CATS = MENU_MEOW
COMMAND_DIE = MENU_DIE
SPECIAL_MONKEY = "🙈"
SPECIAL_LAUGH = "😂"
ACTION_ON = "on"
ACTION_OFF = "off"
ACTION_CANCEL = "back"
ACTIONS = [ACTION_ON, ACTION_OFF, ACTION_CANCEL]


class Bot(object):
    def __init__(self, ha_ip, ha_passw, tg_token):
        self.alive = True
        self.bot = telegram.Bot(token=tg_token)
        self.api = remote.API(ha_ip, ha_passw)

        try:
            remote.validate_api(self.api)
            self.bot.getMe()
        except:
            self.teardown()

        try:
            self.last_update_id = self.bot.getUpdates()[-1].update_id
        except IndexError:
            self.last_update_id = None
        #except telegram.TelegramError:
            #self.last_update_id = None
        self.sensors = self.get_homeassistant_sensors()

        # access control
        self.trusted_users = []
        self.admins = []
        self.token = ''.join(random.choice(
                             string.ascii_lowercase + string.ascii_uppercase +
                             string.digits)
                             for x in range(10))

    def teardown(self):
        self.alive = False

    def get_token(self):
        return self.token

    def trust_user(self, user, giveadmin):
        self.trusted_users.append(user)
        if giveadmin:
            self.admins.append(user)
            print("Gave " + str(user) + " extended privileges")  # DEBUG

    def get_trusted_users(self):
        return self.trusted_users

    def get_admins(self):
        return self.admins

    def is_trusted_user(self, user):
        return user in self.trusted_users

    def is_admin(self, user):
        return user in self.admins

    def loop(self):
        log = []

        self.sensors = self.get_homeassistant_sensors()
        updates = self.bot.getUpdates(offset=self.last_update_id)
        for update in updates:
            self.last_update_id = update.update_id + 1
            if not update.message:
                continue
            user = update.message.from_user
            text = update.message.text

            log.append(str(user.id) + ": " + text)

            answer = self.parse_message(user, text)

            print(update.message.to_dict())

            if answer[0] == COMMAND_CATS:
                caturl = self.get_kitten()
                print(caturl)  # DEBUG
                self.bot.sendChatAction(chat_id=update.message.chat_id,
                                        action=telegram.ChatAction.UPLOAD_PHOTO)
                self.bot.sendPhoto(chat_id=update.message.chat_id,
                                   photo=caturl)
                #continue

            if answer[0] == COMMAND_DIE:
                self.teardown()
                updates = self.bot.getUpdates(offset=self.last_update_id)  # DEBUG
                answer[0] = "Bye!"

            if update.message.chat.type != "private":
                answer[1] = "" #None  # TODO

            if len(answer[0]):
                self.bot.sendMessage(chat_id=update.message.chat_id,
                                     reply_markup=answer[1],
                                     text=answer[0])

        return log

    def parse_message(self, user, text):
        if text == self.token:
            self.trust_user(user.id, False)
            return "Access granted", None
        if not self.is_trusted_user(user.id):
            return "Access denied", None

        arguments = text.split(" ")
        menu = arguments.pop(0)
        buttons = self.create_buttons(menu, arguments, self.is_admin(user.id))
        keyboard = telegram.ReplyKeyboardMarkup(self.align_buttons(buttons))
        reply = self.create_reaction(menu, arguments, self.is_admin(user.id))

        return [reply, keyboard]

    def create_buttons(self, menu, arguments, admin_access):
        if not admin_access:
            return [MENU_MEOW]

        # user's default keyboard
        buttons = [MENU_STATES, MENU_SWITCHES, MENU_MEOW, MENU_DIE]

        if menu == MENU_STATES:
            buttons = [MENU_STATES_SUB + " " + key
                       for key in self.sensors.keys()]
        if menu == MENU_SWITCHES:
            buttons = [MENU_SWITCH_SUB + " " + switch["id"]
                       for switch in self.sensors["switch"]]
        if menu == MENU_STATES_SUB:
            buttons = [COMMAND_STATE + " " + sensor["id"]
                       for sensor in self.sensors[arguments[0]]]
        if menu == MENU_SWITCH_SUB:
            if not len(arguments):
                return
            for switch in self.sensors["switch"]:
                if switch["id"] == arguments[0]:
                    buttons = [COMMAND_SWITCH + " " + switch["id"] +
                               " " + action for action in ACTIONS]

        print(buttons)
        return buttons

    def align_buttons(self, buttons):
        keyboard = []
        row = 0
        # TODO: rewrite this keyboard part
        while len(buttons) / KEYBOARD_WIDTH + 1 > row:
            keyboard.append(
                buttons[row*KEYBOARD_WIDTH:(row+1)*KEYBOARD_WIDTH])
            row += 1
        if row == 0:
            keyboard = None

        return keyboard

    def create_reaction(self, menu, arguments, admin_access):
        if menu == MENU_MEOW:
            return COMMAND_CATS

        if SPECIAL_MONKEY in menu or SPECIAL_MONKEY in arguments:
            return SPECIAL_MONKEY
        if SPECIAL_LAUGH in menu or SPECIAL_LAUGH in arguments:
            return "🙉"

        if not admin_access:
            return ""

        if menu == MENU_DIE:
            return COMMAND_DIE

        if menu == MENU_SWITCH_SUB:
            for switch in self.sensors["switch"]:
                if switch["id"] == arguments[0]:
                    return switch["state"]

        if menu == COMMAND_STATE:
            for sensortype in self.sensors:
                for sensor in self.sensors[sensortype]:
                    if sensor["id"] == arguments[0]:
                        return sensor["state"]

        if not len(arguments) < 2:
            if menu == COMMAND_SWITCH and arguments[1] != ACTION_CANCEL:
                action = ""
                if arguments[1] == ACTION_ON:
                    action = "turn_on"
                if arguments[1] == ACTION_OFF:
                    action = "turn_off"
                remote.call_service(self.api, "switch", action,
                                    {"entity_id": arguments[0]})
                return "ok"

        if menu == MENU_STATES or menu == MENU_SWITCHES \
                or menu == MENU_STATES_SUB or menu == COMMAND_SWITCH:
            return "What do you want to do?"

        return ""

    # returns a dict:
    #   keys are the sensor types
    #   values are lists of sensor dicts:
    #     "id": the name, "state": the state
    def get_homeassistant_sensors(self):
        # retrieve and sort sensors
        sensors = dict()
        for state in remote.get_states(self.api):
            sensortype = state.entity_id.split(".")[0]
            if sensortype not in sensors:
                sensors[sensortype] = []
            sensors[sensortype].append({
                "state": state.state,
                "id": state.entity_id
            })

        return sensors

    def get_kitten(self):
        while True:
            r = requests.get("http://thecatapi.com/api/images/get")
            if r.status_code == 200:
                return r.url


def main_loop(sc):
    if homebot.alive:
        logs = homebot.loop()
        if len(logs):
            for log in logs:
                print(log)
        sc.enter(1, 1, main_loop, (sc,))
    else:
        with open(ACL_FILE, "w") as f:
            for u in homebot.get_trusted_users():
                f.write(str(u) + "\n")
            for u in homebot.get_admins():
                f.write("!" + str(u) + "\n")

if __name__ == "__main__":
    homebot = Bot(IP, PASSW, TOKEN)
    with open(ACL_FILE, "r") as f:
        for u in f:
            isadmin = False
            user = u.rstrip("\n")
            if not len(user):
                continue
            if user[0] == "!":
                isadmin = True
                user = user[1:]
            homebot.trust_user(int(user), isadmin)

    print("Send " + homebot.get_token() + " to register.")
    sc = sched.scheduler(time.time, time.sleep)
    sc.enter(1, 1, main_loop, (sc,))
    sc.run()
