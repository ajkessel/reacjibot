This is a [Maubot](https://github.com/maubot/maubot) for use in a [Matrix](https://matrix.org/) chat room. The plugin allows you to define arbitrary emoji reactions that will cause messages tagged with the specified emoji to be automatically cross-posted to a different room.

You'll need to create a config.yaml (based on [example-config.yaml](example-config.yaml)) to specific mappings. For example:
```
mapping:
  - "train":"public_transportation"
```
Will cause any message tagged with the train emoji :train: to be posted to teh local room with the alias #public_transportation.

See the [Emoji List](emoji_list.md) for the short emoji names used by this library.
