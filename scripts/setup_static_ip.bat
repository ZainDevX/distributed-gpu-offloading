@echo off
REM ============================================================================
REM Static IP Configuration Helper for Direct Peer-to-Peer LAN (CAT6 / Wi-Fi)
REM Course: CSC-334 Parallel and Distributed Computing
REM ============================================================================

echo ============================================================================
echo   DISTRIBUTED GPU OFFLOADING - PEER-TO-PEER IP SETUP HELPER (CSC-334)
echo ============================================================================
echo.
echo Select Configuration Mode:
echo [1] Configure as WORKER NODE (Server: 192.168.1.1 / 255.255.255.0)
echo [2] Configure as CLIENT NODE (Client: 192.168.1.2 / 255.255.255.0)
echo [3] Revert Network Adapter to Automatic DHCP
echo [4] Display Current Active Network Interfaces
echo.
set /p mode="Enter choice [1-4]: "

if "%mode%"=="4" (
    netsh interface ipv4 show addresses
    pause
    exit /b 0
)

echo.
echo Available Network Interfaces:
netsh interface show interface
echo.
set /p iface="Enter Exact Interface Name (e.g., 'Ethernet' or 'Wi-Fi'): "

if "%mode%"=="1" (
    echo.
    echo Configuring %iface% as WORKER NODE (Static IP: 192.168.1.1)...
    netsh interface ipv4 set address name="%iface%" static 192.168.1.1 255.255.255.0
    echo Configuration complete!
)

if "%mode%"=="2" (
    echo.
    echo Configuring %iface% as CLIENT NODE (Static IP: 192.168.1.2)...
    netsh interface ipv4 set address name="%iface%" static 192.168.1.2 255.255.255.0 192.168.1.1
    echo Configuration complete!
)

if "%mode%"=="3" (
    echo.
    echo Reverting %iface% to automatic DHCP...
    netsh interface ipv4 set address name="%iface%" dhcp
    echo Reset to DHCP complete!
)

echo.
echo New IP Configuration for %iface%:
netsh interface ipv4 show addresses name="%iface%"
pause
