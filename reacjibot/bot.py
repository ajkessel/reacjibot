# reacjibot
# Copyright 2024 Adam J. Kessel
# MIT license
from typing import Awaitable, Type, Tuple
import re

from mautrix.client import Client
from mautrix.types import (Event, MessageType, EventID, UserID, FileInfo, EventType, RoomID,
        MediaMessageEventContent, TextMessageEventContent, ContentURI,
        MatrixURI, ReactionEvent, RedactionEvent, ImageInfo, RelationType,
        EncryptedEvent)
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
        helper.copy("insecure")
        helper.copy("template")

class ReacjiBot(Plugin):
    reacji: dict        # reacji->room mappings
    crossposted: dict   # cache of cross-posted messages 
    encrypted: dict     # cache of room encryption settings
    allowed: dict       # cache of users allowed to cross-post
    insecure: bool      # are users allowed to post from encrypted to unencrypted rooms
    restrict: bool      # are only identified users allow to cross-post
    debug: bool         # preference for debug logging
    repost: bool        # preference for reposting tagged messages
    template: str       # template for cross-posting messages

# UpdateReacji: re-process emoji->room mappings and look up rooms as required
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
                    self.debug and self.log.debug(f"no valid room mapping found for {room}")
                    room = ""
            self.debug and self.log.debug(f"mapping {key} to {room}")
            self.reacji[key] = room

# IsEncrypted: check if room_id is an encrypted room, used if insecure is set to false
    async def IsEncrypted(self, room_id) -> None:
        self.debug and self.log.debug(f"checking for encryption on {room_id}")
        if room_id in self.encrypted:
            return self.encrypted[room_id]
        else:
            try:
                if await self.client.get_state_event(room_id, EventType.ROOM_ENCRYPTION):
                    is_encrypted = True
            except:
                is_encrypted = False
            self.encrypted[room_id] = is_encrypted
            return is_encrypted

# start: load initial configuration and do sanity check
    async def start(self) -> None:
        self.config.load_and_update()
        self.reacji = {}
        self.crossposted = {}
        self.encrypted = {}
        self.allowed = {}
        self.debug = False
        self.insecure = True
        self.restrict = False
        self.repost = False
        self.template = '[%on](%ol): %m \n\n (%b)'
        try:
            self.debug = self.config["debug"]
            self.debug and self.log.debug(f"verbose debugging enabled in config.yaml")
            if self.config['template']:
                self.template = self.config["template"]
                self.debug and self.log.debug(f"got template {self.template}")
            else: 
                self.debug and self.log.debug(f"using default template")
            self.insecure = self.config["insecure"]
            self.restrict = self.config["restrict_users"]
            if self.restrict:
                self.allowed = self.config["allowed_users"]
        except:
            self.log.debug(f"error in configuration file: {error}")
        await self.UpdateReacji()

    async def on_external_config_update(self) -> None:
        await self.start()

# generic_react: called when a reaction to a message event occurs; main guts of the plugin
# TODO - find a better regexp that only matches emojis
    @command.passive(regex=re.compile(r"[^A-Za-z0-9]"), field=lambda evt: evt.content.relates_to.key, event_type=EventType.REACTION, msgtypes=None)
    async def generic_react(self, evt: ReactionEvent, key: Tuple[str]) -> None:
        if self.restrict and evt.sender not in self.allowed:
            self.debug and self.log.debug(f"user {evt.sender} not allowed to cross-post")
            return
        source_evt = await self.client.get_event(evt.room_id, evt.content.relates_to.event_id)
        symbol = evt.content.relates_to.key
        if not self.insecure:
            is_source_encrypted = await self.IsEncrypted(evt.room_id)
        for key in self.reacji:
            if re.match(key,symbol):
                 # assemble cross-post string if matching reacji is found
                target_id = self.reacji[key]
                # check if this is an insecure cross-post and if so whether that is allowed
                if not self.insecure and is_source_encrypted and not await self.IsEncrypted(target_id):
                    self.debug and self.log.debug(f"insecure cross-posting not allowed, skipping")
                    continue
                # first check to make sure this is not a re-post; if it has already been posted and repost is not true, skip
                if not self.repost and evt.content.relates_to.event_id in self.crossposted:
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
                message = self.template
                message = message.replace('%on',displayname)
                message = message.replace('%ol',str(userlink))
                message = message.replace('%m',body)
                message = message.replace('\\n',chr(10))
                message = message.replace('%b',str(xlinkback))
                self.debug and self.log.debug(f"posting {message} to {target_id}")
                await self.client.send_markdown(target_id,message)
                # add post to the crossposted dictionary to avoid future reposts
                self.crossposted[evt.content.relates_to.event_id] = {}
                self.crossposted[evt.content.relates_to.event_id][target_id] = True
                break

    @classmethod
    def get_config_class(cls) -> Type[BaseProxyConfig]:
        return Config
