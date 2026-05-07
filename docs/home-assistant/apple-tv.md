# Home Assistant Apple TV Automation

This automation posts Apple TV viewing starts into the datalake as `watch.started` events.

Use it when the Apple TV is already available through Home Assistant's `media_player` entity and you want a reliable record of what started playing, regardless of which app supplied it.

## What it sends

- `source`: `apple_tv`
- `event_type`: `watch.started`
- `timestamp`: the current HA time in ISO 8601 format
- `payload`: media metadata captured from the Apple TV entity

Recommended payload fields:

- `title`
- `series_title`
- `season`
- `episode`
- `app_name`
- `app_id`
- `content_type`
- `duration_seconds`

## Home Assistant config

```yaml
# configuration.yaml or a package file
automation:
  - alias: "Push Apple TV watch start to datalake"
    mode: queued
    trigger:
      - platform: state
        entity_id: media_player.apple_tv  # change to your Apple TV entity
        attribute: media_title
        for:
          seconds: 2  # debounce reconnect flicker and rapid title updates
    condition:
      - condition: state
        entity_id: media_player.apple_tv
        state: "playing"
      - condition: template
        value_template: >
          {{ trigger.to_state.attributes.media_title not in ['', None] }}
    action:
      - service: rest_command.datalake_push_apple_tv
        data:
          title: "{{ state_attr('media_player.apple_tv', 'media_title') }}"
          series_title: "{{ state_attr('media_player.apple_tv', 'media_series_title') | default('') }}"
          season: "{{ state_attr('media_player.apple_tv', 'media_season') | default(none) }}"
          episode: "{{ state_attr('media_player.apple_tv', 'media_episode') | default(none) }}"
          app_name: "{{ state_attr('media_player.apple_tv', 'app_name') }}"
          app_id: "{{ state_attr('media_player.apple_tv', 'app_id') }}"
          content_type: "{{ state_attr('media_player.apple_tv', 'media_content_type') | default('') }}"
          duration: "{{ state_attr('media_player.apple_tv', 'media_duration') | default(none) }}"

rest_command:
  datalake_push_apple_tv:
    url: "http://docker.home:8000/events"
    method: POST
    headers:
      Authorization: !secret datalake_token
      Content-Type: application/json
    payload: >
      {
        "source": "apple_tv",
        "event_type": "watch.started",
        "timestamp": "{{ now().isoformat() }}",
        "payload": {
          "title": "{{ title }}",
          "series_title": {{ ('"' ~ series_title ~ '"') if series_title else 'null' }},
          "season": {{ season if season != 'None' else 'null' }},
          "episode": {{ episode if episode != 'None' else 'null' }},
          "app_name": "{{ app_name }}",
          "app_id": "{{ app_id }}",
          "content_type": "{{ content_type }}",
          "duration_seconds": {{ duration if duration != 'None' else 'null' }}
        }
      }
```

## Secrets

Set `datalake_token` in `secrets.yaml` to the same value as the API token used by the datalake stack.

```yaml
datalake_token: "your-shared-token"
```

## Why this trigger

The Apple TV state can fall back to `idle` or `standby` unpredictably when playback changes, so the automation watches `media_title` while the player stays in `playing`. That captures starts reliably without depending on a clean playback end event.

## Example event shape

```json
{
  "source": "apple_tv",
  "event_type": "watch.started",
  "timestamp": "2026-05-07T20:00:00+02:00",
  "payload": {
    "title": "Goodbye, Mrs. Selvig",
    "series_title": "Severance",
    "season": 2,
    "episode": 5,
    "app_name": "Netflix",
    "app_id": "com.netflix.Netflix",
    "content_type": "tvshow",
    "duration_seconds": 3120
  }
}
```
