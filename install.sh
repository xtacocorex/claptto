#!/bin/sh

echo "INSTALLING CLAPTTO"
cp claptto.py /root
cp -r gifserver /root
cp -r init.d /etc/init.d

echo "REBOOTING"
reboot

