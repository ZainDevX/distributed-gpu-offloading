#!/usr/bin/env bash
# ==============================================================================
# Static IP Configuration Helper for Direct Peer-to-Peer LAN (Linux/macOS)
# Course: CSC-334 Parallel and Distributed Computing
# ==============================================================================

set -e

echo "=============================================================================="
echo "  DISTRIBUTED GPU OFFLOADING - PEER-TO-PEER IP SETUP HELPER (CSC-334)"
echo "=============================================================================="
echo ""
echo "Select Configuration Mode:"
echo "1) Configure as WORKER NODE (Server: 192.168.1.1/24)"
echo "2) Configure as CLIENT NODE (Client: 192.168.1.2/24)"
echo "3) Display Current Active Network Interfaces"
read -p "Enter choice [1-3]: " mode

if [ "$mode" = "3" ]; then
    ip -br addr show
    exit 0
fi

echo ""
echo "Available Network Interfaces:"
ip -br link show
echo ""
read -p "Enter Network Interface Name (e.g. eth0, enp3s0): " iface

if [ "$mode" = "1" ]; then
    echo "Configuring $iface as WORKER NODE (192.168.1.1/24)..."
    sudo ip addr flush dev "$iface"
    sudo ip addr add 192.168.1.1/24 dev "$iface"
    sudo ip link set "$iface" up
    echo "Worker static IP configured successfully!"
fi

if [ "$mode" = "2" ]; then
    echo "Configuring $iface as CLIENT NODE (192.168.1.2/24)..."
    sudo ip addr flush dev "$iface"
    sudo ip addr add 192.168.1.2/24 dev "$iface"
    sudo ip link set "$iface" up
    echo "Client static IP configured successfully!"
fi

echo ""
echo "Updated interface state:"
ip addr show dev "$iface"
