"""
Description : Python script intents to write the software stack infos on the wallpaper.
Autor   : Yang
Date    : 7/31
"""
#-*- coding: utf-8 -*-

import os
import sys
import textwrap
import wmi
import win32api,win32con,win32gui
from collections import OrderedDict
from PIL import Image, ImageDraw, ImageFont


def set_wallpaper_from_bmp(bmp_path):
    '''
    Set the wallpaper with the windows api
    '''
    #open the register key 
    reg_key = win32api.RegOpenKeyEx(win32con.HKEY_CURRENT_USER,"Control Panel\\Desktop",0,win32con.KEY_SET_VALUE)
    #set the parameter of the wallpaper style
    win32api.RegSetValueEx(reg_key, "WallpaperStyle", 0, win32con.REG_SZ, "2")
    win32api.RegSetValueEx(reg_key, "TileWallpaper", 0, win32con.REG_SZ, "0")
    #fresh the Desktop with the new picture
    win32gui.SystemParametersInfo(win32con.SPI_SETDESKWALLPAPER,bmp_path, 1+2)

def get_sysinfo():
    '''
    Get the system information
    '''
    sysinfo = OrderedDict()
    CalculateMemory = 0
    CalculateDisk = 0
    CalculateFreeDisk = 0
    wmiservice = wmi.WMI()
    sysinfo['HostName'] = os.getenv('COMPUTERNAME')
    for sys in wmiservice.Win32_OperatingSystem():
        sysinfo['Operation System'] = sys.Caption.encode("UTF8") + sys.OSArchitecture.encode("UTF8")
    for Memory in wmiservice.Win32_PhysicalMemory(): 
        CalculateMemory += int(Memory.Capacity)/1048576/1024
    sysinfo['Total Memory'] = str(CalculateMemory) + " GB"
    for Disk in wmiservice.Win32_LogicalDisk (DriveType=3):
        CalculateDisk += int(Disk.size)/1048576/1024
        CalculateFreeDisk += int(Disk.FreeSpace)/1048576/1024
    sysinfo['Total Dsikspace'] = str(CalculateDisk) + " GB"
    sysinfo['Availabe Diskspace'] = str(CalculateFreeDisk) + " GB"
    return sysinfo
          
def get_installerinfo(installer_path):
    '''
    Get the software stack from the log
    '''
    try:
        with open(installer_path,'r') as fn:
            content = fn.read()
            return content
    except Exception :
        return "No installation information"
    
def draw_wallpaper(img_path,installerinfo,systeminfo):
    '''
    Write the info to the wallpaper including hardwares, software stack
    '''
    font = ImageFont.truetype(r'C:\Windows\Fonts\arial.ttf',20)
    im = Image.open(img_path)
    draw = ImageDraw.Draw(im)
        #Write the system info
    draw.text((1000,100), "System Infomation:",font=font, fill=(0,230,230,250))
    pos_top = 110
    height = 23
    for info in systeminfo:
        pos_top += height*1.2
        draw.text((1050,pos_top), info + ":  " + systeminfo[info],font=font, fill=(0,0,100,100))

    #Write the hardwares info
    pos_top_2 = (pos_top + 40)
    draw.text((1000,pos_top_2), "Available Hardwares:",font=font, fill=(0,230,230,250))
    pos_top_2 += 10
    if os.getenv('COMPUTERNAME') in Hardwares.keys():
        for hardware in Hardwares[os.getenv('COMPUTERNAME')]:
            pos_top_2 += height*1.2
            draw.text((1050,pos_top_2), hardware,font=font, fill=(0,0,100,100))
    else:
        pass

    #Write the software stack info
    pos_top_3 = (pos_top_2 + 40)
    draw.text((1000,pos_top_3), "Software Stack:",font=font, fill=(0,230,230,250))
    pos_top_3 += 10
    for text in textwrap.wrap(installerinfo,width=80):
        pos_top_3 += height*1.1
        draw.text((1050,pos_top_3), text,font=font, fill=(0,0,100,100))
    #Save the drawed wallpaper as C:\rfststest.bmp
    im.save(r'C:\rfststest.bmp','BMP')

def set_wallpaper(img_path,installer_path):
    '''
    Set the wallpaper
    '''
    systeminfo = get_sysinfo()
    installerinfo = get_installerinfo(installer_path)
    draw_wallpaper(img_path,installerinfo,systeminfo)
    set_wallpaper_from_bmp(r'C:\rfststest.bmp')
 
if __name__== '__main__':
    #Dictionary stored the mapping between machine name and devices.
    Hardwares = {'RFSTS_VST_01':['VST_5646R','SMU_4139'],\
                'RFSTS_RFPM_01':['RFPM_5530','VST_5646R'],\
                'RFSTS_T2_01':['RFPM_5530','VST_5646R*2','HSD_6570','SMU_4139','DMM_4081','PPS_4110'],\
                'RFSTS_T2_02':['RFPM_5530','VST_5646R','VST_5820','HSD_6570','FGEN_5451','RIO_7976R','DMM_4081','SMU_4139*3','SMU_4145','PPS_4110']}
    #Original wallpaper
    img_path = r'C:\Windows\Web\Wallpaper\Windows\img0.jpg'
    if len(sys.argv) > 1:
        installer_path = sys.argv[1]
    else:
        installer_path = r'C:\installer.log'
    set_wallpaper(img_path,installer_path)