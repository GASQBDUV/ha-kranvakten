"""Konstanter för Lerum VA."""

from datetime import timedelta

DOMAIN = "lerum_va"

CONF_CUSTOMER_ID = "customer_id"
CONF_PERSONAL_NUMBER = "personal_number"
CONF_BASE_URL = "base_url"

DEFAULT_BASE_URL = "https://vatjanst.lerum.se/FutureWebBasic"

# Portalen uppdateras bara när mätaren läses av, så det räcker att fråga sällan.
UPDATE_INTERVAL = timedelta(days=30)
