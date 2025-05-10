---
sidebar_position: 4
---

# Killmail Subscription

Subscribe to killmail notifications for specific characters, corporations, alliances, systems, or ship types.

## Conditional Subscription

Command format:

`/sub add <type> <name> [-a <attack threshold>] [-v <victim threshold>]`

Supported types:
- `char`/`Character`: Character
- `corp`/`Corporation`: Corporation
- `alli`/`Alliance`: Alliance
- `system`/`System`: System
- `ship`/`Ship`: Ship type

Parameter description:
- `-a/--attack`: Set the attack threshold (ISK), default is 30 million
- `-v/--victim`: Set the victim threshold (ISK), default is 30 million

Example:

`/sub add corp TestCorp -a 50000000 -v 100000000`

## Remove Subscription

Command format:

`/sub remove <type> <name>`

## High-Value Subscription

Subscribe to all killmails above a specific value:

`/sub_high <value>`

Remove high-value subscription:

`/sub_high -r`

## Display Effect

![Killmail Notification](/img/docs/features/km-subscription/km.png)