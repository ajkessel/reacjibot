This is a [Maubot](https://github.com/maubot/maubot) plugin for use in a [Matrix](https://matrix.org/) chat room. The plugin allows you to define arbitrary emoji reactions that will cause messages tagged with the specified emoji to be automatically cross-posted to a different room.

**Important security warning**: the current implementation will post from any room to any other room, regardless of encryption. So, depending on how you configure it, you could have it post from an encrypted room to a non-encrypted room. I'll work on making this configurable in the future.

You'll need to create a config.yaml (based on [example-config.yaml](example-config.yaml)) to specify mappings. For example:
```
mapping:
  🚋: 'public_transportation'
```
Will cause any message tagged with the train emoji 🚋 to be posted to the local room with the alias #public_transportation. You can define as many actions as you want, although currently the system is limited to posting to one room per emoji reaction.

Note the YAML parser is fussy and needs a space after the colon for the mapping to work correctly. You will also need to put the room name in quotes if you use the fully qualified room name (!room_id:server.tld) as opposed to the alias.

## TODO items

* add configuration to disallow cross-posting from encrypted to unencrypted rooms
* add in-room commands to define mappings
* allow custom template for cross-posting
* cull back unnecessary libraries
* allow multiple room posting with single emoji
