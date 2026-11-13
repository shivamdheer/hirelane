# Connecting Google

Google is optional. Without it you still get the local database, the web interface and the digest file. Connecting adds
Sheets tracking, Gmail reply tracking, the digest by email, and calendar slot proposals.

You bring your own OAuth client, so Hirelane carries no Google credentials. The steps take about ten minutes.

## 1. Create a project and enable the APIs

1. Open the Google Cloud console and create a project, for example `hirelane-personal`.
2. Under APIs and Services, then Library, enable the Google Sheets API, the Gmail API and the Google Calendar API.

## 2. Configure the consent screen

1. Under APIs and Services, then OAuth consent screen, choose External and fill in the app name and your email.
2. Add these scopes:
   - `https://www.googleapis.com/auth/spreadsheets`
   - `https://www.googleapis.com/auth/gmail.readonly`
   - `https://www.googleapis.com/auth/gmail.send`
   - `https://www.googleapis.com/auth/calendar.readonly`
3. Add your own address as a test user.

## 3. Publish the app so tokens do not expire

While an app is in Testing status, Google expires its refresh tokens after 7 days, and `hirelane inbox` will start to
fail with a refused token. To avoid that, go back to the OAuth consent screen and choose **Publish app** so the status
becomes In production. The app stays unverified and only you use it, so you will see a warning screen once during
sign-in. Choose Advanced, then continue to the app.

## 4. Create the client

1. Under Credentials, choose Create credentials, then OAuth client ID.
2. Choose Desktop app and download the JSON file.

## 5. Connect

```
pip install 'hirelane[google]'
hirelane google connect --client-file ~/Downloads/client_secret_example.json
```

A browser window asks you to sign in and approve the scopes. The client and the token are stored in your system keyring.
The downloaded file can then be deleted. Check with `hirelane google status`.

## What each feature does

| Command | Effect |
| --- | --- |
| `hirelane inbox` | Reads the last two days of mail, classifies replies and updates jobs. Read only. |
| `hirelane digest` | Also emails the digest to your own address. `--no-email` skips that. |
| `hirelane sheet` | Writes a tracking sheet and applies approve or skip decisions typed in column L. |
| `hirelane slots` | Prints free half hour slots from your calendar for a scheduling reply. |

Gmail send is used for one thing, the digest, and the recipient is always the address in your profile.

## Disconnect

`hirelane google disconnect` removes the token from the keyring and turns the feature off. You can also revoke access
from your Google account's security page.
