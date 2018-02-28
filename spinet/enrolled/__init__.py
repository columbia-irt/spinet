import os
from .. import wpas, ipv6

# Global variables for the enrollment daemon

ifname    = 'wlan0'                 # Main interface name
name      = None                    # Node name (can be set to hostname)
db        = None                    # Global SQLite database object
db_path   = '/data/enrolled.db'     # Path to the SQlite3 database file
addr      = ipv6.random_addr_ipv4()      # The IP address for the HTTP API to listen on
port      = 10000                   # The port number for the HTTP API to listen on
verbose   = False                   # Enable/disable debugging
sup       = wpas.P2PWPASupplicant() # Global WPASupplicant instance
on        = sup.on                  # Decorator for event receivers from the main WPASupplicant object
crt_path  = '/data/cert.pem'        # Path to the file with the device's certificate
key_path  = '/data/key.pem'         # Path to the file with the device's private key
ip        = None                    # IP address
