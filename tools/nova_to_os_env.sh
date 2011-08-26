# This file is intended to be sourced to convert old-style NOVA environment
# variables to new-style OS.
#
# The plan is to add this to novarc, but until that lands, it's useful to have
# this in Glance.
export OS_AUTH_USER=$NOVA_USERNAME
export OS_AUTH_KEY=$NOVA_API_KEY
export OS_AUTH_TENANT=$NOVA_PROJECT_ID
export OS_AUTH_URL=$NOVA_URL
export OS_AUTH_STRATEGY=$NOVA_AUTH_STRATEGY
