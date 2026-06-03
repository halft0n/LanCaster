; LanCaster Windows Installer (NSIS)
; Build: makensis installer\lancaster.nsi
; Expects PyInstaller output at dist\LanCaster\

!include "MUI2.nsh"
!include "FileFunc.nsh"

; --- General ---
Name "LanCaster"
OutFile "..\dist\LanCaster-Setup.exe"
InstallDir "$PROGRAMFILES\LanCaster"
InstallDirRegKey HKLM "Software\LanCaster" "InstallDir"
RequestExecutionLevel admin
Unicode True

; --- Version Info ---
!define PRODUCT_NAME "LanCaster"
!define PRODUCT_VERSION "0.1.2"
!define PRODUCT_PUBLISHER "LanCaster Contributors"
!define PRODUCT_WEB "https://github.com/halft0n/LanCaster"

VIProductVersion "0.1.2.0"
VIAddVersionKey "ProductName" "${PRODUCT_NAME}"
VIAddVersionKey "ProductVersion" "${PRODUCT_VERSION}"
VIAddVersionKey "FileDescription" "LanCaster DLNA Casting Tool"
VIAddVersionKey "LegalCopyright" "MIT License"

; --- MUI Settings ---
!define MUI_ABORTWARNING
!define MUI_ICON "..\assets\icon.ico"
!define MUI_UNICON "..\assets\icon.ico"

; --- Pages ---
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_LICENSE "..\LICENSE"
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

!insertmacro MUI_LANGUAGE "SimpChinese"
!insertmacro MUI_LANGUAGE "English"

; --- Install Section ---
Section "Install"
    SetOutPath "$INSTDIR"

    ; Copy all PyInstaller output
    File /r "..\dist\LanCaster\*.*"

    ; Create uninstaller
    WriteUninstaller "$INSTDIR\Uninstall.exe"

    ; Start Menu shortcuts
    CreateDirectory "$SMPROGRAMS\LanCaster"
    CreateShortCut "$SMPROGRAMS\LanCaster\LanCaster.lnk" "$INSTDIR\LanCaster.exe" "" "$INSTDIR\LanCaster.exe"
    CreateShortCut "$SMPROGRAMS\LanCaster\卸载 LanCaster.lnk" "$INSTDIR\Uninstall.exe"

    ; Desktop shortcut
    CreateShortCut "$DESKTOP\LanCaster.lnk" "$INSTDIR\LanCaster.exe" "" "$INSTDIR\LanCaster.exe"

    ; Registry entries for Add/Remove Programs
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\LanCaster" \
        "DisplayName" "LanCaster"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\LanCaster" \
        "UninstallString" "$\"$INSTDIR\Uninstall.exe$\""
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\LanCaster" \
        "DisplayIcon" "$INSTDIR\LanCaster.exe"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\LanCaster" \
        "Publisher" "${PRODUCT_PUBLISHER}"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\LanCaster" \
        "DisplayVersion" "${PRODUCT_VERSION}"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\LanCaster" \
        "URLInfoAbout" "${PRODUCT_WEB}"

    ; Compute installed size
    ${GetSize} "$INSTDIR" "/S=0K" $0 $1 $2
    IntFmt $0 "0x%08X" $0
    WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\LanCaster" \
        "EstimatedSize" "$0"

    WriteRegStr HKLM "Software\LanCaster" "InstallDir" "$INSTDIR"
SectionEnd

; --- Uninstall Section ---
Section "Uninstall"
    ; Remove files
    RMDir /r "$INSTDIR"

    ; Remove shortcuts
    Delete "$DESKTOP\LanCaster.lnk"
    RMDir /r "$SMPROGRAMS\LanCaster"

    ; Remove registry keys
    DeleteRegKey HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\LanCaster"
    DeleteRegKey HKLM "Software\LanCaster"
SectionEnd
