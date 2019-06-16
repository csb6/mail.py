# mail.py

A very basic email client written in Python supporting IMAP/SMTP. It is currently a work
in progress and is not ready for use. To experiment with the current development code,
switch to the `imap` branch.

## Usage

- After cloning, create a file named `config.json` with the following structure:
```
{
     "host": "",
     "username": "",
     "password": ""
}
```

- Look up the hostname for your email provider, then fill out the JSON file.

- For Gmail addresses, you need to create an app-specific password. Go to
![your security preferences](https://myaccount.google.com/security) and create
a password. Copy this password into the JSON.

- Currently, there is support for downloading ~25 messages from your inbox, displaying
the emails onscreen, and sending emails by clicking on the `Compose` button at the
top of the screen. The messages are stored in a local database file, `mail.db`, which
you can freely delete in order to resync your inbox.

- As stated earlier, this program is not currently in a usable state, so core features
like email syncing, multiple mailboxes, and drafts are not yet available.
