#!/bin/bash

echo Begin to take snapshot

if [ -z "$1" ]; then
    echo invalid parameter >> TakeSnapshot.log 2>&1
    exit 2
fi

sudo python ./TakeSnapshot.py "$1" >> TakeSnapshot.log 2>&1