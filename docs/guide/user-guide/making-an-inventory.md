# Making an inventory of your files

Data Director never sees your data files. To help with a README, a data dictionary or a metadata
record, it needs facts about the files instead: an **inventory**. You make the inventory on the
computer where the data are, then attach it to a message in the app.

## What an inventory holds

For each file under a folder, the inventory records:

- its path within the folder, such as `raw/site-a.csv`, and never where the folder is on your
  computer;
- its size, and a digest (a fingerprint) that later shows the files you deposit are the files
  described;
- its format;
- for a table (CSV or TSV), its column names and types, worked out from a sample of rows.

It never holds what is in a file. It is a JSON file that you can open and read before you attach
it. Hidden files and folders (names beginning with `.`) are left out, and the inventory says so.

## Making one

You need [uv](https://docs.astral.sh/uv/getting-started/installation/), a tool that installs and
runs Python programs. Once it is installed, open a terminal and run this command, replacing
`path/to/dataset` with the folder that holds your data:

```console
uvx --from "git+https://github.com/data-director-agent/data-director#subdirectory=inventory" dd-inventory path/to/dataset -o inventory.json
```

It writes `inventory.json` in the folder where you ran it. A large dataset can take a while,
because every file is read to compute its digest. The command sends nothing anywhere.

If you would rather not use a terminal, ask your research data support team, or whoever is
running a workshop you are in, to make the inventory for you.

## Attaching it in the app

On the conversation page, select **Attach inventory** under the message box and choose
`inventory.json`. You can also drop the file onto the message box. The inventory shows as a chip
naming how many files it lists and when it was made. Select **View inventory** on the chip to
read everything it holds before you send it: the folders and files, their sizes and formats, and
the column names of each table. That is all Data Director keeps of your data. Write your
request, such as "Please draft a README for this dataset", and send it. You can also send the
inventory on its own.

The conversation's project keeps the inventory, so you attach it once. Data Director gives it to
the agents that need it. If your files change, make a new inventory and attach it: the latest one
counts. The panel beside the conversation shows which inventory the project holds, with
**View inventory** to read it again, and links to the documents agents have drafted.

See [What the Data Director records](records.md) for who can see what you attach.
