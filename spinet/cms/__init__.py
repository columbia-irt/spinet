import os
from .. import wpas, ipv6

# Global variables for the commissioner

ifname  = 'wlan0'                 # Main interface name
name    = os.uname()[1]           # Node name (can be set to hostname)
db      = None                    # Global SQLite database object
db_path = '/data/commissioner.db' # Path to the SQlite3 database file
verbose = False                   # Enable/disable debugging
sup     = wpas.P2PWPASupplicant() # Global WPASupplicant instance
on      = sup.on                  # Decorator for event receivers from the main WPASupplicant object
addr    = ipv6.random_addr()
