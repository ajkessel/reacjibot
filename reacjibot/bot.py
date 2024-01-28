from typing import Awaitable, Type, Tuple
import re

from mautrix.client import Client
from mautrix.types import (Event, MessageType, EventID, UserID, FileInfo, EventType, RoomID,
                            MediaMessageEventContent, TextMessageEventContent, ContentURI,
                            MatrixURI, ReactionEvent, RedactionEvent, ImageInfo, RelationType)
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
               # assemble cross-post string if matching reacji is found
              target_id = self.reacji[key]
               # first check to make sure this is not a re-post; if it has already been posted and repost is not true, skip
              if not self.config["repost"] and evt.content.relates_to.event_id in self.crossposted:
                 if target_id in self.crossposted[evt.content.relates_to.event_id]:
                    self.debug and self.log.debug(f"event {source_evt.content.body} already cross-posted, skipping")
                    continue
               # displayname: the display name for the original poster
              displayname = await self.client.get_displayname(source_evt.sender)
               # userlink: a hyperlink to the original poster's user ID
              userlink = MatrixURI.build(source_evt.sender)
               # body: the contents of the message to be cross-posted
              body = source_evt.content.body
               # xdisplayname: the display name of the person cross-posting
              xdisplayname = await self.client.get_displayname(evt.sender)
               # xuserlink: a hyperlink to the cross-poster's user ID
              xuserlink = MatrixURI.build(evt.sender)
               # xmessage: a hyperlink to the original message
              xmessage = MatrixURI.build(evt.room_id, EventID(evt.content.relates_to.event_id))
               # xlink: link to the original message as displayed, with an emoji icon as the link
              xlink = f"[{key}]({xmessage})"
               # xlinkback: the full hyperlinked string to the original message
              xlinkback = f"{xlink} by {xuserlink}"
               # message: the full message to be posted in the new room
              message = f"[{displayname}]({userlink}): {body} {chr(10)}{chr(10)} ({xlinkback})"
              self.debug and self.log.debug(f"posting {message} to {target_id}")
              await self.client.send_markdown(target_id,message)
               # add post to the crossposted dictionary to avoid future reposts
              self.crossposted[evt.content.relates_to.event_id] = {}
              self.crossposted[evt.content.relates_to.event_id][target_id] = "1"
              break

    @classmethod
    def get_config_class(cls) -> Type[BaseProxyConfig]:
        return Config
