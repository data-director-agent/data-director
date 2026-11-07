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

It never holds what is in a file. It does hold **the names of your files and folders** and **the
column headings of your tables**, and these can say more than you expect: a file named after a
participant, a folder named after a place, or a column called `hiv_status`. Agents may show the
inventory to an AI model hosted outside your institution; it is the one part of your project that
may go to such a model unless your institution says otherwise. Before you attach it, the app shows
you everything in it and lets you leave out anything that should not leave your computer.

Hidden files and folders (names beginning with `.`) are left out, and the inventory says so.

## Making one

<!-- making-an-inventory:summary -->

In the app, select **Make an inventory** under the message box on the conversation page. It shows
these steps for the computer you are using, with a button to copy each command, and ends with a
button to attach the file you made. The steps are the same here:

<!-- making-an-inventory:steps -->

If you prefer pip, install the command once with `pip install data-director-inventory`, then run
`data-director-inventory path/to/dataset -o inventory.json`. The package is published on
[PyPI](https://pypi.org/project/data-director-inventory/).

It writes `inventory.json` in the folder where you ran it. A large dataset can take a while,
because every file is read to compute its digest. The command sends nothing anywhere.

If you would rather not use a terminal, ask your research data support team, or whoever is
running a workshop you are in, to make the inventory for you.

## Attaching it in the app

On the conversation page, select **Attach inventory** under the message box and choose
`inventory.json`, or select **Choose inventory.json** at the end of **Make an inventory**. You can
also drop the file onto the message box.

The app then shows you everything the inventory holds, before anything is kept: the folders and
files, their sizes and formats, and the column names of each table. That is all Data Director
will keep of your data, and all that agents will see. Each file, folder and column has an
**Include** tick box. Untick anything you would rather not share, such as a folder of consent
forms or a column whose name is sensitive; leaving out a folder leaves out everything in it. Use
**Find files** to look for a name in a large inventory. When you are content, select **Attach
this inventory**. If you select **Cancel**, nothing is attached.

What you leave out is not sent or kept anywhere, not even its name. The inventory says only how
many files and columns you left out, so that an agent does not assume they do not exist.

The inventory then shows as a chip naming how many files it lists and when it was made. Select
**View inventory** on the chip to read it again. Write your request, such as "Please draft a
README for this dataset", and send it. You can also send the inventory on its own.

The conversation's project keeps the inventory, so you attach it once. Data Director gives it to
the agents that need it. If your files change, make a new inventory and attach it: the latest one
counts. The panel beside the conversation shows which inventory the project holds, with
**View inventory** to read it again, and links to the documents agents have drafted.

See [What the Data Director records](records.md) for who can see what you attach.
