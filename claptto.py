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
VIDDEV = "/dev/video0"
RESO = "640x480" #"1280x720"
LOOP_COUNT = 0
DELAY = 35
NOTIFY_ON_TIME = 0.3
NOTIFY_LOOP_COUNT = 4

# GLOBAL VARIABLES
printonce = True
pic_count = 0

# THREADING EVENT FOR ALLOWING
# THE CLAP DETECTION
shutterevent = threading.Event()
shutterevent.clear()
imageevent = threading.Event()
imageevent.clear()
makegifevent = threading.Event()
makegifevent.clear()
notifyevent = threading.Event()
notifyevent.clear()

# CLASSES
class Combiner(threading.Thread):
    def __init__(self, loop_count, delay):
        threading.Thread.__init__(self)
        self.loop_count = loop_count
        self.delay = delay
        self.dead = False
        self.gifcmd = "convert -loop {0} -delay {1} /tmp/int_pic_*.png /root/gifserver/static/claptto_pic_{2}.gif"

    def kill(self):
        self.dead = True

    # COMBINE TO A GIF
    def make_gif(self):
        while imageevent.isSet():
            pass

        print("WE BE MAKIN THOSE GIFS YOU SEE")
        ctime = int(datetime.datetime.utcnow().strftime("%s"))
        mycmd = self.gifcmd.format(self.loop_count, self.delay, ctime)
        mycmd = mycmd.split()
        print(mycmd)
        imageevent.set()
        # MAKE GIF
        subprocess.call(mycmd)
        print("GREAT GIF DUDE!")
        notifyevent.set()
        imageevent.clear()

    # REMOVE THE INTERIM PNG
    def remove_interim_png(self):
        globber = "/tmp/int_*.png"
        gobs = glob.glob(globber)
        for g in gobs:
            os.remove(g)

    def run(self):
        while not self.dead:
            while not makegifevent.isSet():
                pass
            if makegifevent.isSet():
                self.make_gif()
                self.remove_interim_png()
                makegifevent.clear()
                notifyevent.set()
        print("COMBINER KILLED")

# NOTIFIER
class Notifier(threading.Thread):
    def __init__(self, gpio, ledpin, ontime, repeats=1):
        threading.Thread.__init__(self)
        self.gpio = gpio
        self.ledpin = ledpin
        self.ontime = ontime
        self.repeats = repeats
        self.dead = False

    def kill(self):
        dead = True

    def run(self):
        while not self.dead:
            while not notifyevent.isSet():
                pass
            if notifyevent.isSet():
                for i in range(self.repeats):
                    self.gpio.output(self.ledpin, 1)
                    time.sleep(self.ontime)
                    self.gpio.output(self.ledpin, 0)
                    time.sleep(self.ontime / 2.0)
                notifyevent.clear()
        print("NOTIFIER KILLED")

# CALLBACK FUNCTION
def shutter_button(channel):
    global printonce
    global pic_count
    pic_count = 0
    if not shutterevent.isSet():
        printonce = True
        shutterevent.set()
        print("SHUTTER PRESSED - ALLOWING PICTURES")
    else:
        printonce = False
        shutterevent.clear()
        print("SHUTTER PRESSED - STOPPING")
        # DO WORK SON
        makegifevent.set()

# CLAP DETERMINER
# LOGIC FROM
# https://github.com/NextThingCo/chiptainer_vu_meter/blob/stable/vu-meter.py
def detect_clap(aud, retries):
    rtnval = False
    retry = 0
    while retry < retries:
        l,data = aud.read()
        if l and shutterevent.isSet():
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

# TAKE SINGLE PICTURE
def take_picture(current_count):
    while imageevent.isSet():
        pass

    print("HERE BE PICTURE TAKIN")
    # QUIET DEVICE RESO NO BANNER PNG 
    mycmd = "fswebcam -q -d {0} -r{1} --no-banner --png 9 /tmp/int_pic_{2:03d}.png".format(VIDDEV, RESO, current_count)
    mycmd = mycmd.split()
    print(mycmd)
    imageevent.set()
    subprocess.call(mycmd)
    imageevent.clear()
    notifyevent.set()
    print("PICTURE DONE!")
    return current_count + 1

# MAIN
def Main():
    # SETUP AUDIO FOR THE CLAPPER
    print("SETTING UP ALSA")
    audinp = alsaaudio.PCM(alsaaudio.PCM_CAPTURE, alsaaudio.PCM_NORMAL, 'default')
    audinp.setchannels(2)
    audinp.setrate(44100)
    audinp.setformat(alsaaudio.PCM_FORMAT_S16_LE)
    audinp.setperiodsize(1024)

    # EXPORT THE SHUTTER PIN AS AN INPUT
    print("EXPORTING SHUTTER PIN")
    GPIO.setup(SHUTTER, GPIO.IN)
    GPIO.add_event_detect(SHUTTER, GPIO.FALLING, shutter_button, bouncetime=200)

    # EXPORT NOTIFIER PIN
    print("EXPORTING SIGNAL PIN")
    GPIO.setup(SIGNAL, GPIO.OUT)

    # CREATE OUR GIF COMBINER
    giffer = Combiner(LOOP_COUNT, DELAY)
    giffer.start()

    signaller = Notifier(GPIO, SIGNAL, NOTIFY_ON_TIME, NOTIFY_LOOP_COUNT)
    signaller.start()

    dead = False
    printonce = True
    pic_count = 0
    try:
        while not dead:
            # LOOP WHILE WE DON"T KNOW ABOUT THE SHUTTER
            while not shutterevent.isSet():
                pass

            # WE GOT THAT SHUTTER BUTTON
            if shutterevent.isSet():
                if printonce:
                    print("CLAP IT UP")
                    printonce = False
                
                # DO THE WORK
                # FIND THE CLAP AND ONLY ALLOW A PICTURE IF WE AREN'T CURRENTLY
                # TAKING ONE
                if detect_clap(audinp, RETRIES) and not imageevent.isSet():
                    print("YAY, CLAP")
                    pic_count = take_picture(pic_count)

    except KeyboardInterrupt:
        dead = True

    # HANDLE CASE WHERE WE WERE IN A PICTURE
    # AND NEED TO FINALIZE IT
    if shutterevent.isSet():
        print("SHUTTER WAS SET WHEN KILLED")
        print("FINALIZING GIF")
        # DO WORK SON
        makegifevent.set()

    # CLEANUP
    print("CLEANUP")
    GPIO.cleanup()
    giffer.kill()
    signaller.kill()

if __name__ == "__main__":
    Main()
