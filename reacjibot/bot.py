from typing import Awaitable, Type, Optional, Tuple
import json
import re
import time
import random

from mautrix.client import Client
from mautrix.types import (Event, MessageType, EventID, UserID, FileInfo, EventType, RoomID,
                            MediaMessageEventContent, TextMessageEventContent, ContentURI,
                            ReactionEvent, RedactionEvent, ImageInfo, RelationType)
from mautrix.util.config import BaseProxyConfig, ConfigUpdateHelper
from maubot import Plugin, MessageEvent
from maubot.handlers import command, event

class Config(BaseProxyConfig):
    def do_update(self, helper: ConfigUpdateHelper) -> None:
        helper.copy("restrict_users")
        helper.copy("allowed_users")
        helper.copy("mapping")
        helper.copy("domain")
        helper.copy("repost")

class ReacjiBot(Plugin):
    async def start(self) -> None:
        self.reacji = {} 
        self.crossposted = {}
        self.config.load_and_update()
        for key in self.config["mapping"]:
            room=self.config["mapping"][key]
            if room.find(":") == -1:
               room = room + ":" + self.config["domain"]
            if room[0] == "#":
               room = room[1:]
            if room[0] != "!":
               try:
                 room = (await self.client.resolve_room_alias('#' + room)).room_id
               except:
                 room = ""
            self.reacji[key] = room

    @command.passive(regex=re.compile(r"[^A-Za-z0-9]"), field=lambda evt: evt.content.relates_to.key, event_type=EventType.REACTION, msgtypes=None)
    async def generic_react(self, evt: ReactionEvent, key: Tuple[str]) -> None:
        if self.config['restrict_users'] and len(self.config['allowed_users']) > 0 and evt.sender not in self.config['allowed_users']:
           return
        source_evt = await self.client.get_event(evt.room_id, evt.content.relates_to.event_id)
        symbol = evt.content.relates_to.key
        for key in self.reacji:
           if re.match(key,symbol):
              message = evt.sender + ": " + source_evt.content.body + ' [' + key + '](' + 'https://matrix.to/#/' + evt.room_id + '/' + evt.content.relates_to.event_id + '?via=' + self.config["domain"] +')'
              target_id = self.reacji[key]
              if not self.config["repost"] and evt.content.relates_to.event_id in self.crossposted:
                 if target_id in self.crossposted[evt.content.relates_to.event_id]:
                    continue
              await self.client.send_markdown(target_id,message)
              self.crossposted[evt.content.relates_to.event_id] = {}
              self.crossposted[evt.content.relates_to.event_id][target_id] = "1"
              break

    @classmethod
    def get_config_class(cls) -> Type[BaseProxyConfig]:
        return Config
