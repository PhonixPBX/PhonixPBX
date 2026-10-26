---
title: "Media"
weight: 40
description: "Music on hold, the voicemail greeting, IVR announcements, recording by phone, text to speech and the prompt language."
---
*Services → Media* holds your own audio files: music on hold, a custom voicemail greeting, and the announcements of IVR menus. It also shows which language the system prompts use.

Uploading or deleting music on hold or the voicemail greeting has to be applied before callers hear the change, see [Applying changes]({{< relref "/getting-started/_index.md#apply" >}}).

## Music on hold {#moh}

Callers hear music on hold while they are held, parked or alone in a conference. Without uploads PhonixPBX plays the bundled music.

Drop one or more audio files onto the *Music on hold* box, or click it to choose files. All uploaded music files form one playlist that is played in random order. As soon as one file is uploaded, the bundled music is no longer used; once you delete the last uploaded file, it is used again.

> Only use music you have the rights to play to callers. Many music licences do not cover public playback on a phone system.

## Voicemail greeting {#greeting}

The voicemail greeting replaces the standard "unavailable" announcement that callers hear before they leave a message. It applies to all mailboxes. There is only one greeting: uploading a new file replaces the old one. Delete it in the file list to return to the standard announcement.

Record a neutral text that fits every mailbox, for example "The person you are calling is not available. Please leave a message after the tone."

## IVR announcements {#ivr}

The announcements of IVR menus are uploaded in the menu editor under [Dialplan → IVR Menus]({{< relref "/dialplan/ivr.md" >}}). They appear here in the file list with the type *IVR announcement*. Deleting an announcement that a menu still uses leaves that menu silent until you choose another announcement; apply the change afterwards.

## Record by phone {#record}

Instead of uploading a file you can speak an IVR announcement or the voicemail greeting into a phone. Under **Record by phone** choose what to **Record** (for an IVR announcement also its **Name**) and the phone under **Ring phone**, then click **Call me**:

1. The PBX calls the phone. Answer it and speak the text after the tone.
2. Press `#` to end the recording. The phone plays it back.
3. Press `1` to save it, `2` to listen again or `3` to record it again.

The page shows each step and, once you pressed `1`, the new file in the list. Hanging up before pressing `1` discards the recording; so does not answering the call. A recording is stored like an uploaded file: an IVR announcement appears in the menu editor, a new voicemail greeting replaces the old one and has to be applied.

Only SIP and IAX phones can be rung. The instructions on the phone are played in the phone's prompt language.

## Create from text {#tts}

A text-to-speech server can speak an IVR announcement or the voicemail greeting for you. Set up the server first under [Text-to-speech server](#tts-server).

Under **Create from text** choose what to **Create** (for an IVR announcement also its **Name**), a **Voice** and the **Speed**, and type the **Text** (up to 2000 characters). **Listen** plays the result in the browser without storing it; **Create** stores it like an uploaded file. A new voicemail greeting replaces the old one and has to be applied.

> The text is sent to the text-to-speech server. Use a server you trust, ideally one in your own network.

## Text-to-speech server {#tts-server}

PhonixPBX uses a server with the RestfulTTS API. It does not ship text-to-speech itself.

| Field | Meaning | Default |
|---|---|---|
| Server address | Base URL of the server, for example `http://tts.example.com:8000`. Empty turns the feature off. | empty |
| Access token | Only if the server requires one; it is sent as a bearer token. Leave the field empty to keep the stored token; changing the server address without a new token removes it. | empty |
| Default voice | The voice used when you do not choose one. Empty: the server's voice for the [prompt language](#prompt-language) of the system. | empty |
| Speed | 0.5 (slow) to 2 (fast). | 1 |
| Timeout (seconds) | How long to wait for the server. | 60 |

The audio is requested in telephone quality (8 kHz mono WAV). Scripts can create announcements from text through the [REST API]({{< relref "/reference/api.md#media" >}}).

## Uploaded files {#files}

The table lists all uploaded files with type, name, size and upload time. Use the download icon to listen to the converted file (WAV) and the trash icon to delete it.

The search field above the list finds files by name or type; how searching and paging work is described in [Lists]({{< relref "/getting-started/_index.md#lists" >}}).

## File formats {#formats}

- Music on hold accepts WAV, MP3, OGG and FLAC files up to 64 MB each; the voicemail greeting WAV, MP3 and OGG up to 16 MB.
- Every upload is converted to 8 kHz, 16 bit mono WAV, the format Asterisk plays without further conversion. Telephone audio is limited to this quality anyway, so high-quality sources bring no benefit.
- For best results, use recordings without long silence at the start and with moderate volume.
- Scripts can upload files as well, through the [REST API]({{< relref "/reference/api.md#media" >}}).

## Prompt language {#prompt-language}

The system announcements (voicemail menus, conference messages, "the number is not available" and so on) are played in the default prompt language. The *Voice prompts* card shows the current language; change it under [System → General Setup]({{< relref "/system/general.md#tones-language" >}}). Each phone can also have its own language.

The firmware ships English prompts. For other languages the English recordings are played as long as no recordings for that language are installed.
