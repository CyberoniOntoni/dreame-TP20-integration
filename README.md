Will need to manually install it as I don't have HASS. If someone would like to configure that feel free. PRs welcome etc  
  
Its a hard fork of the AP10 integration, I am open w/ regards to merging the two into one Dreame\_Purifier integration, Also encouraged if someone has experience with HA

AI assisted, I've looked over the codebase, I've been using it for a while w/o any issues, still use at your own risk etc. You will need to set up a username/number & password for your Dreame account, no oauth

It *should* support the PM20, short of the heat settings which are exclusive to that model. It shouldn't be too difficult to reverse engineer, there are some scripts in the repo to assist with snooping the api

I haven't gotten around to updating the rest of the README, but just follow the manual instructions

> clone repo  
> copy [custom\_components/dreame\_airpurifier](https://github.com/shaunsingh/dreame-pm10-integration/tree/main/custom_components/dreame_airpurifier) to HA `config/custom_components/` e.x. `~/.config/homeassistant/config/custom_components/dreame_airpurifier\`, create it if it isnt already there

Restart HA, settings->devices & services -> add integration -> search dreame & fill out details

There is some issue w/ the Dreame API being IPv4 only & conflicting w/ tail scale if it's an exit node so keep that in mind. YMMV. open an issue if you have issues

I really just made this so I could use the climate sensors for HA automations. I was hoping it would expose the builtin MMWAVE radar used for the Follow mode. Good news privacy enthusiasts, that is all handled locally. Bad news HA enthuasists, that is all handled locally.
