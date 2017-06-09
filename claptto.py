#!/usr/bin/env python

# COPYRIGHT 2017
# ROBERT WOLTERMAN (CAMERA CODE)
# COPYRIGHT 2016 NEXTTHINGCO
# COPYRIGHT 2011 UDO KLEIN 

# MODULE IMPORTS
import CHIP_IO.GPIO as GPIO
import threading
import alsaaudio
import audioop
import math
import datetime
import subprocess
import glob
import os
import time

# CONSTANTS
LO = math.log(2000)
HI = math.log(20000)
VAL_MAX = 100
VAL_MIN = 0
VAL_TRIGGER = 65
SHUTTER = "EINT24"
SIGNAL = "CSID0"
RETRIES = 10
DEVICE = "/dev/video0"
RESO = "640x480" #"1280x720"
LOOP_COUNT = 0
DELAY = 20
NOTIFY_ON_TIME = 0.3
NOTIFY_LOOP_COUNT = 4
GIF_DIRECTORY = "/mnt/pictures"
TMP_DIRECTORY = "/tmp_images"

# GLOBAL VARIABLES
printonce = True

# CLASSES
class Claptto(threading.Thread):
    def __init__(self, gpio, device, reso, loop_count, delay):
        threading.Thread.__init__(self)
        self.gpio = gpio
        self.device = device
        self.reso = reso
        self.pic_count = 0
        self.loop_count = loop_count
        self.delay = delay
        self.dead = False
        self.in_clap_session = False
        self.in_image_session = False
        self.piccmd = "fswebcam -q -d {0} -r{1} --no-banner --png 9 {2}/int_pic_{3:03d}.png"
        self.pngtogifcmd = "convert {0}/int_pic_{1:03d}.png {2}/int_pic_{3:03d}.gif"
        #self.gifcmd = "convert -loop {0} -delay {1} {2}/int_pic_*.png {3}/claptto_pic_{4}.gif"
        self.gifcmd = "gifsicle --loopcount --delay={0} --colors 256 {1}/*.gif -o {2}/claptto_pic_{3}.gif"
        # CHECK FOR THE DIRECTORY TO STORE MOVIES
        self._directory_check()

    def _directory_check(self):
        if not os.path.exists(GIF_DIRECTORY):
            print("CREATING GIF DIRECTORY")
            os.makedirs(GIF_DIRECTORY)
        if not os.path.exists(TMP_DIRECTORY):
            print("CREATING TEMPORARY PNG DIRECTORY")
            os.makedirs(TMP_DIRECTORY)

    def kill(self):
        self.dead = True
        # FORCE THIS TO BE FALSE TO KICK US OUT
        self.in_clap_session = False

    def setup_alsa(self):
        # SETUP AUDIO FOR THE CLAPPER
        print("SETTING UP ALSA")
        self.audinp = alsaaudio.PCM(alsaaudio.PCM_CAPTURE, alsaaudio.PCM_NORMAL, 'default')
        self.audinp.setchannels(2)
        self.audinp.setrate(44100)
        self.audinp.setformat(alsaaudio.PCM_FORMAT_S16_LE)
        self.audinp.setperiodsize(1024)

    def setup_gpio(self, pin):
        # EXPORT THE SHUTTER PIN AS AN INPUT
        print("EXPORTING SHUTTER PIN")
        self.gpio.setup(pin, self.gpio.IN)
        self.gpio.add_event_detect(pin, self.gpio.FALLING, self.shutter_button, bouncetime=200)

    def setup_notifier(self, ledpin, ontime, repeats=1):
        self.ledpin = ledpin
        self.ontime = ontime
        self.repeats = repeats
        # EXPORT NOTIFIER PIN
        print("EXPORTING SIGNAL PIN")
        self.gpio.setup(self.ledpin, self.gpio.OUT)

    def do_notify(self, repeats):
        for i in range(repeats):
            self.gpio.output(self.ledpin, 1)
            time.sleep(self.ontime)
            self.gpio.output(self.ledpin, 0)
            time.sleep(self.ontime / 2.0)

    # COMBINE TO A GIF
    def make_gif(self):
        while self.in_image_session:
            pass

        print("WE BE MAKIN THOSE GIFS YOU SEE")
        ctime = int(datetime.datetime.utcnow().strftime("%s"))
        # FFMPEG
        #mycmd = self.gifcmd.format(self.loop_count, self.delay, TMP_DIRECTORY, GIF_DIRECTORY, ctime)
        # GIFSICLE
        mycmd = self.gifcmd.format(self.delay, TMP_DIRECTORY, GIF_DIRECTORY, ctime)
        print(mycmd)
        self.in_image_session = True
        # MAKE GIF
        subprocess.call(mycmd.split())
        print("GREAT GIF DUDE!")
        self.do_notify(3)
        self.in_image_session = False

    # REMOVE THE INTERIM PNG
    def remove_interim_images(self):
        globber = "{0}/int_*.*".format(TMP_DIRECTORY)
        gobs = glob.glob(globber)
        for g in gobs:
            os.remove(g)

    # TAKE SINGLE PICTURE
    def take_picture(self):
        while self.in_image_session:
            pass

        print("HERE BE PICTURE TAKIN")
        # QUIET DEVICE RESO NO BANNER PNG 
        mycmd = self.piccmd.format(self.device, self.reso, TMP_DIRECTORY, self.pic_count)
        mycmd = mycmd.split()
        print(mycmd)
        self.in_image_session = True
        subprocess.call(mycmd)
        self.in_image_session = False
        print("PICTURE DONE!")
        self.do_notify(1)
        # CONVERT FROM PNG TO GIF
        mycmd = self.pngtogifcmd.format(TMP_DIRECTORY, self.pic_count, TMP_DIRECTORY, self.pic_count)
        mycmd = mycmd.split()
        print(mycmd)
        self.pic_count += 1

    # CLAP DETERMINER
    # LOGIC FROM
    # https://github.com/NextThingCo/chiptainer_vu_meter/blob/stable/vu-meter.py
    def detect_clap(self, retries):
        rtnval = False
        retry = 0
        while retry < retries:
            l,data = self.audinp.read()
            if l and self.in_clap_session:
                try:
                    lchannel=audioop.tomono(data, 2, 1, 0)
                    rchannel=audioop.tomono(data, 2, 0, 1)
                    lvu = (math.log(float(max(audioop.max(lchannel, 2),1)))-LO)/(HI-LO)
                    rvu = (math.log(float(max(audioop.max(rchannel, 2),1)))-LO)/(HI-LO)
                    lval = min(max(int(lvu*VAL_MAX),VAL_MIN),VAL_MAX)
                    rval = min(max(int(rvu*VAL_MAX),VAL_MIN),VAL_MAX)
                    if rval >= VAL_TRIGGER or lval >= VAL_TRIGGER:
                        rtnval = True
                        break
                except:
                    retry += 1

        return rtnval

    # CALLBACK FUNCTION
    def shutter_button(self, channel):
        global printonce
        if not self.in_clap_session:
            printonce = True
            print("SHUTTER PRESSED - ALLOWING PICTURES")
            self.in_clap_session = True
        else:
            printonce = False
            print("SHUTTER PRESSED - STOPPING")
            self.in_clap_session = False
            # DO WORK SON
            self.make_gif()
            self.remove_interim_images()
            self.pic_count = 0

    def run(self):
        while not self.dead:
            while not self.in_clap_session:
                if self.dead:
                    break
                else:
                    pass
            if self.in_clap_session:
                if self.detect_clap(RETRIES) and not self.in_image_session:
                    print("YAY, CLAP")
                    self.take_picture()
        print("CLAPTTO KILLED")

# MAIN
def Main():
    # CREATE OUR GIF CAMERA
    claptto = Claptto(GPIO, DEVICE, RESO, LOOP_COUNT, DELAY)
    claptto.setup_alsa()
    claptto.setup_gpio(SHUTTER)
    claptto.setup_notifier(SIGNAL, NOTIFY_ON_TIME, NOTIFY_LOOP_COUNT)
    claptto.start()

    dead = False
    try:
        while not dead:
            pass

    except KeyboardInterrupt:
        dead = True

    # CLEANUP
    print("CLEANUP")
    claptto.kill()
    GPIO.cleanup()

if __name__ == "__main__":
    Main()
