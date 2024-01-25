from typing import Awaitable, Type, Tuple
import re

from mautrix.client import Client
from mautrix.types import (Event, MessageType, EventID, UserID, FileInfo, EventType, RoomID,
                            MediaMessageEventContent, TextMessageEventContent, ContentURI,
                            ReactionEvent, RedactionEvent, ImageInfo, RelationType)
from mautrix.util.config import BaseProxyConfig, ConfigUpdateHelper
from maubot import Plugin, MessageEvent
from maubot.handlers import command, event

class Config(BaseProxyConfig):
    def do_update(self, helper: ConfigUpdateHelper) -> None:
        helper.copy("debug")
        helper.copy("restrict_users")
        helper.copy("allowed_users")
        helper.copy("mapping")
        helper.copy("domain")
        helper.copy("repost")

class ReacjiBot(Plugin):
    reacji: dict
    crossposted: dict
    debug: bool
    async def UpdateReacji(self) -> None:
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
                 self.debug and self.log.debug(f"no room mapping found for {room}")
                 room = ""
            self.debug and self.log.debug(f"mapping {key} to {room}")
            self.reacji[key] = room

    async def start(self) -> None:
        self.config.load_and_update()
        self.reacji = {}
        self.crossposted = {}
        self.debug = self.config["debug"]
        self.debug and self.log.debug(f"verbose debugging enabled in config.yaml")
        await self.UpdateReacji()

    async def on_external_config_update(self) -> None:
        self.config.load_and_update()
        await self.UpdateReacji()

    @command.passive(regex=re.compile(r"[^A-Za-z0-9]"), field=lambda evt: evt.content.relates_to.key, event_type=EventType.REACTION, msgtypes=None)
    async def generic_react(self, evt: ReactionEvent, key: Tuple[str]) -> None:
        if self.config['restrict_users'] and len(self.config['allowed_users']) > 0 and evt.sender not in self.config['allowed_users']:
           self.debug and self.log.debug(f"user {evt.sender} not allowed to cross-post")
           return
        source_evt = await self.client.get_event(evt.room_id, evt.content.relates_to.event_id)
        symbol = evt.content.relates_to.key
        for key in self.reacji:
           if re.match(key,symbol):
              message = source_evt.sender + ": " + source_evt.content.body + ' [' + key + '](' + 'https://matrix.to/#/' + evt.room_id + '/' + evt.content.relates_to.event_id + '?via=' + self.config["domain"] +')'
              target_id = self.reacji[key]
              if not self.config["repost"] and evt.content.relates_to.event_id in self.crossposted:
                 if target_id in self.crossposted[evt.content.relates_to.event_id]:
                    self.debug and self.log.debug(f"event {source_evt.content.body} already cross-posted, skipping")
                    continue
              self.debug and self.log.debug(f"posting {message} to {target_id}")
              await self.client.send_markdown(target_id,message)
              self.crossposted[evt.content.relates_to.event_id] = {}
              self.crossposted[evt.content.relates_to.event_id][target_id] = "1"
              break

    @classmethod
    def get_config_class(cls) -> Type[BaseProxyConfig]:
        return Config
