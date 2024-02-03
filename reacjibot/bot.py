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
        helper.copy("images")

class ReacjiBot(Plugin):
    reacji: dict        # reacji->room mappings
    crossposted: dict   # cache of cross-posted messages 
    encrypted: dict     # cache of room encryption settings
    allowed: dict       # cache of users allowed to cross-post
    insecure: bool      # are users allowed to post from encrypted to unencrypted rooms
    restrict: bool      # are only identified users allow to cross-post
    debug: bool         # preference for debug logging
    repost: bool        # preference for reposting tagged messages
    images: bool        # preference for crossposting images
    template: str       # template for cross-posting messages
    base_command: str   # command for talking to the bot
    base_aliases: Tuple[str, ...]   # aliases for bot base command

# UpdateReacji: re-process emoji->room mappings and look up rooms as required
    async def UpdateReacji(self) -> None:
        for key in self.config["mapping"]:
            room = await self.MapRoom(self.config["mapping"][key])
            self.reacji[key] = room
            self.debug and self.log.debug(f"mapping {key} to {room}")

# MapRoom: find room ID based on alias or fully qualified room name
    async def MapRoom(self, room_candidate: str) -> str:
        if room_candidate.find(":") == -1:
            room_candidate = room_candidate + ":" + self.config["domain"]
        if room_candidate[0] == "#":
            room_candidate = room_candidate[1:]
        if room_candidate[0] != "!":
            try:
                room_candidate = (await self.client.resolve_room_alias('#' + room_candidate)).room_id
            except:
                self.debug and self.log.debug(f"no valid room mapping found for {room_candidate}")
                room_candidate = ""
        return room_candidate

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
        self.images = True
        self.base_command = 'reacji'
        self.template = '[%on](%ol): %m \n\n ([%e](%bl) by [%bu](%bi))'
        try:
            self.debug = self.config["debug"]
            self.debug and self.log.debug(f"verbose debugging enabled in config.yaml")
            bc = self.config["base_command"]
            self.base_command = bc[0] if isinstance(bc, list) else bc
            self.base_aliases = tuple(bc) if isinstance(bc, list) else (bc,)
            if self.config['template']:
                self.template = self.config["template"]
                self.debug and self.log.debug(f"got template {self.template}")
            else: 
                self.debug and self.log.debug(f"using default template")
            self.insecure = self.config["insecure"]
            self.restrict = self.config["restrict_users"]
            self.images = self.config["images"]
            if self.restrict:
                self.allowed = self.config["allowed_users"]
        except:
            self.log.debug(f"error in configuration file: {error}")
        await self.UpdateReacji()

    async def on_external_config_update(self) -> None:
        await self.start()

# generic_react: called when a reaction to a message event occurs; main guts of the plugin
    @command.passive(regex=re.compile('[\U00010000-\U0010ffff]+', flags=re.UNICODE), field=lambda evt: evt.content.relates_to.key, event_type=EventType.REACTION, msgtypes=None)
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
                # name of the room original message was posted in
                roomnamestate = await self.client.get_state_event(source_evt.room_id, 'm.room.name')
                rn = str(roomnamestate['name'])
                # userlink: a hyperlink to the original poster's user ID
                userlink = str(MatrixURI.build(source_evt.sender))
                # body: the contents of the message to be cross-posted
                body = source_evt.content.body
                # xdisplayname: the display name of the person cross-posting
                xdisplayname = await self.client.get_displayname(evt.sender)
                # xuserlink: a hyperlink to the cross-poster's user ID
                xuserlink = str(MatrixURI.build(evt.sender))
                # xmessage: a hyperlink to the original message
                xmessage = str(MatrixURI.build(evt.room_id, EventID(evt.content.relates_to.event_id)))
                # message: the full message to be posted in the new room
                message = self.template
                message = message.replace('\\n',chr(10))
                message = message.replace('%on',displayname)
                message = message.replace('%ol',userlink)
                message = message.replace('%m',body)
                message = message.replace('%e',key)
                message = message.replace('%bl',xmessage)
                message = message.replace('%bu',xdisplayname)
                message = message.replace('%bi',xuserlink)
                message = message.replace('%rn',rn)
                try:
                    self.debug and self.log.debug(f"posting {message} to {target_id}")
                    if source_evt.content.msgtype == MessageType.IMAGE:
                        if self.images:
                            # TODO - implement better (customizable) interface when the cross-posted content is an image
                           await self.client.send_markdown(target_id,message)
                           await self.client.send_message(target_id,source_evt.content)
                    else:
                        await self.client.send_markdown(target_id,message)
                    # add post to the crossposted dictionary to avoid future reposts
                    self.crossposted[evt.content.relates_to.event_id] = {}
                    self.crossposted[evt.content.relates_to.event_id][target_id] = True
                except:
                    self.debug and self.log.debug(f"message posting failed due to {error}")
                break

    @classmethod
    def get_config_class(cls) -> Type[BaseProxyConfig]:
        return Config

    @command.new(name=lambda self: self.base_command,
                 aliases=lambda self, alias: alias in self.base_aliases,
                 help="Interact with reacjibot", require_subcommand=False)
    async def reacji(self, evt: MessageEvent) -> None:
        await evt.reply(f"reacjibot at your service\n\n!{self.base_command} help for help\n")

    @reacji.subcommand("help", help="Usage instructions")
    async def help(self, evt: MessageEvent) -> None:
        await evt.reply(f"Maubot [Reacjibot](https://github.com/ajkessel/reacjibot) plugin.\n\n"
                        f"* !{self.base_command} map emoji room_name - map emoji to room\n"
                        f"* !{self.base_command} delete emoji - remove emoji mapping\n"
                        f"* !{self.base_command} list [optional emoji name] - list reacji mappings\n"
                        f"* !{self.base_command} help - this message\n")

    @reacji.subcommand("list", help="List reacji mappings")
    @command.argument("emojus", pass_raw=False, required=False)
    async def list(self, evt: MessageEvent, emojus: str) -> None:
        mappings=""
        if emojus:
            try:
                xroom = str(MatrixURI.build(self.reacji[emojus]))
                mappings = mappings + f"* {emojus} to {xroom}\n"
            except:
                mappings = f"* {emojus} is not mapped\n"
        else:
            for key in self.reacji:
                xroom = str(MatrixURI.build(self.reacji[key]))
                mappings = mappings + f"* {key} to {xroom}\n"
        await evt.reply(mappings)
        return

    @reacji.subcommand("map", help="Define a emoji-room mapping")
    @command.argument("mapping", pass_raw=True, required=True)
    async def map(self, evt: MessageEvent, mapping: str) -> None:
        if self.restrict and evt.sender not in self.allowed:
            await evt.reply(f"Sorry, you are not allowed to configure reacjibot. Please ask your site administrator for permission.\n")
            self.debug and self.log.debug(f"user {evt.sender} not allowed to configure")
            return
        try:
            x = mapping.split(" ")
            re_emoji = re.compile('[\U00010000-\U0010ffff]+', flags=re.UNICODE)
            re_html = re.compile(r'<.*?>')
            emoji = re_emoji.findall(x[0])
            room_candidate = re_html.sub('',x[1])
            room = await self.MapRoom(room_candidate)
            xroom = str(MatrixURI.build(room))
        finally: 
            if not emoji or not room:
               await evt.reply(f"error, invalid mapping {mapping}")
               return
            for emojus in emoji:
               await evt.reply(f"mapping {emojus} to {xroom}")
               self.reacji[emojus] = room
               self.config["mapping"][emojus] = room
            self.config.save()
        return

    @reacji.subcommand("delete", help="Delete a emoji-room mapping", aliases=("del","erase","unmap"))
    @command.argument("mapping", pass_raw=True, required=True)
    async def delete(self, evt: MessageEvent, mapping: str) -> None:
        if self.restrict and evt.sender not in self.allowed:
            await evt.reply(f"Sorry, you are not allowed to configure reacjibot. Please ask your site administrator for permission.\n")
            self.debug and self.log.debug(f"user {evt.sender} not allowed to configure")
            return
        try:
            x = mapping.split(" ")
            re_emoji = re.compile('[\U00010000-\U0010ffff]+', flags=re.UNICODE)
            emoji = re_emoji.findall(x[0])
        finally: 
            if not emoji:
               await evt.reply(f"error, invalid delete command {mapping}")
               return
            for emojus in emoji:
               try:
                  del self.reacji[emojus]
                  del self.config["mapping"][emojus]
                  await evt.reply(f"deleting mapping for {emojus}")
               except:
                  await evt.reply(f"{emojus} is not mapped")
            self.config.save()
        return
