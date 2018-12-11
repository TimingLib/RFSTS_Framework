#include <GUIConstants.au3>
#include <Msgboxconstants.au3>
#include <WindowsConstants.au3>
#include <GuiButton.au3>
#include <File.au3>
#include <FileConstants.au3>
#include <Array.au3>
#include <StringConstants.au3>
#include <Process.au3>
#include <AutoItConstants.au3>


;Store the background image
FileInstall("C:\Users\yliu3\Desktop\RemoteWin\Capture2.JPG",@TempDir&"\",1)

;Func CreateGui()
Global $w_Table = GUICreate("Arconis Wrapper",350,250,-1,-1,-1, $WS_DISABLED + $WS_CLIPCHILDREN)
Local  $backimg = @TempDir&"\Capture2.JPG"
Local  $backwall = GUICtrlCreatePic($backimg,0,0,350,200)
GUICtrlSetState($backwall,$GUI_DISABLE)
Local $i_Backup = GUICtrlCreateButton("Back Up", 20, 202, 60, 25)
GUICtrlSetBkColor($i_Backup,0xDCDCDC)
Local $i_Recover = GUICtrlCreateButton("Recover",100, 202, 60, 25)
GUICtrlSetBkColor($i_Recover,0xDCDCDC)
Local $i_Menu = GUICtrlCreateMenu("Setting")
Local $i_Server = GUICtrlCreateMenuItem("Location",$i_Menu)
GUISetState(@SW_show, $w_Table)
WinActivate($w_Table)

Global $location = "D:\Backups"
Global $image = ""

;Func Create the location setting child Gui
Func _Server_Gui()
Global $s_List = GUICreate("add location",250,100,20,20,-1,$WS_EX_MDICHILD,$w_Table)
$i_Input = GUICtrlCreateInput($location,25,40,150,20,-1,$WS_EX_OVERLAPPEDWINDOW)
$i_Button = GUICtrlCreateButton("OK",190,40,45,20,$BS_NOTIFY)
GUISetState(@SW_show,$s_List)
While 1
   Switch GUIGetMsg()
	  Case $GUI_EVENT_CLOSE, $i_Button
		 $location = GUICtrlRead($i_Input)
		 GUIDelete($s_List)
		 ExitLoop
   EndSwitch
WEnd
EndFunc

Dim Const $sMessage = " Please Select the Image"

;Main
While 1
   If not FileExists($location) Then
	  DirCreate($location)
	  If @error Then
		 MsgBox(16,"ERROR","Exception  :  Invalid Path ")
		 ExitLoop
	  EndIf
   EndIf
   Switch GUIGetMsg()
	  Case $GUI_EVENT_CLOSE
			Exit
	  Case $i_Server
			_Server_Gui()
	  Case $i_Recover
			Local $sFileOpenDialog = FileOpenDialog($sMessage, $location, "Images (*.tibx)", $FD_PATHMUSTEXIST)
			$sFileOpenDialog = StringSplit($sFileOpenDialog, "\")
			_ArrayReverse($sFileOpenDialog)
			$image = StringReplace($sFileOpenDialog[0],".tibx","")
			; Display the list of selected files.
			if $image Then
			   $i_Box = MsgBox(1+32, "", "Are you sure that the computer will reboot?")
			   Switch $i_Box
				  Case $IDOK
					 $cmd = 'acrocmd recover disk --volume="C" --loc="' & $location & '" --arc="' &  $image & '" --target_volume="C" --reboot'
					 $rcmdpid = Run(@ComSpec & " /c " & $cmd, "", @SW_HIDE, $STDERR_CHILD)
					 ProcessWaitClose($rcmdpid)
					 $erroinfo = StderrRead($rcmdpid)
					 If $erroinfo Then
						MsgBox(16,"ERROR",$erroinfo)
					 EndIf
					 ExitLoop
			   EndSwitch
			EndIf
	  Case $i_Backup
			Local $sFileSaveDialog = FileSaveDialog($sMessage, $location, "Images (*.*)",$FD_PATHMUSTEXIST + $FD_PROMPTOVERWRITE)
			$sFileSaveDialog = StringSplit($sFileSaveDialog, "\")
			_ArrayReverse($sFileSaveDialog)
			$image = $sFileSaveDialog[0]
			; Display the list of selected files.
			If $image Then
			   WinSetState($w_Table,"",@SW_MINIMIZE )
			   $cmd = 'acrocmd backup disk --volume="C" --loc="' & $location & '" --arc="' & $image & '"'
			   if FileExists($location & "\" & $image & '.tibx') Then
				  FileDelete($location & "\" & $image & '.tibx')
			   ElseIf FileExists($location & "\" & $image) Then
				  FileDelete($location & "\" & $image)
			   EndIf
			   Sleep(500)
			   $bcmdpid = Run(@ComSpec & " /c " & $cmd, "", @SW_HIDE, $STDERR_CHILD)
			   ProcessWaitClose($bcmdpid)
			   $erroinfo = StderrRead($bcmdpid)
			   If $erroinfo Then
				  MsgBox(16,"ERROR",$erroinfo)
			   EndIf
			   ExitLoop
			EndIf
   EndSwitch
WEnd

GUIDelete($w_Table)
Exit 0