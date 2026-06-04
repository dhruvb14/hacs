from __future__ import annotations

DOMAIN = "ir_remote"

# Config entry data keys
CONF_RECEIVER = "receiver"
CONF_NAME = "name"
CONF_FINGERPRINT = "fingerprint"

# Options keys (all timing windows in seconds)
OPT_DEBOUNCE_WINDOW = "debounce_window"
OPT_NEW_PRESS_WINDOW = "new_press_window"
OPT_DOUBLE_CLICK_WINDOW = "double_click_window"
OPT_LEARN_TIMEOUT = "learn_timeout"
OPT_IMMEDIATE_SINGLE = "immediate_single"

# Defaults
DEFAULT_DEBOUNCE_WINDOW = 0.15
DEFAULT_NEW_PRESS_WINDOW = 0.25
DEFAULT_DOUBLE_CLICK_WINDOW = 1.3
DEFAULT_LEARN_TIMEOUT = 20.0
DEFAULT_IMMEDIATE_SINGLE = True
