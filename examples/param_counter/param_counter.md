# param_counter specification

## Inputs

| Name | Type |
|------|------|
| `enable` | bool |

## State

| Name | Kind | Type | Initial |
|------|------|------|---------|
| `count` | register | bits<5> | 0 |

## Behavior (rules)

- **tick** — when enable, set `count` to mod(`count` + 1, 16).

## Properties

- **tick_wraps** (transition): after each step, `count` equals mod(prev(count) + 1, 16).
