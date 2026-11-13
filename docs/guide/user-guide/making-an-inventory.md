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

On the conversation page, select **Attach a file** under the message box and choose
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

You can also tell Data Director what the inventory command cannot know. Select **Describe** under
a file to say what it is, and what part it plays: data, documentation, code or something else.
When the command could not be sure of a file's format (it found several possible formats, only
guessed from the name, or found none), you can choose the right one there too. Open a folder to
set the part every file in it plays at once, and open a table under **Tables** to describe its
columns. Agents use what you write when they describe your dataset, so it is kept and shown to
them just as file names are: do not write anything there that you would not share. **Undo** and
**Redo** step through your changes, and **Show** can narrow the list to the files worth a look.

The inventory then shows as a chip naming how many files it lists and when it was made. Select
**View inventory** on the chip to read it again. Write your request, such as "Please draft a
README for this dataset", and send it. You can also send the inventory on its own.

The conversation's project keeps the inventory, so you attach it once. Data Director gives it to
the agents that need it.

## Changing it later

In the panel beside the conversation, select **Edit inventory** to open the project's inventory
again. You can leave out more, or describe more, and then select **Save as the project's
inventory**. The project keeps the new version, and the earlier one stays in its history.

If your files change, make a new inventory and choose it under **Replace with a new scan of the
same folder**. What you said about each file is carried over to the new scan wherever the file is
still there, and the app tells you which files are new, changed or gone. One thing cannot be
carried over: anything you left out before was never kept, so it appears again in the new scan.
Check the files marked **New in this scan** and leave them out again if you need to. The panel beside the conversation shows which inventory the project holds, with
**View inventory** to read it again, and links to the documents agents have drafted.

See [What the Data Director records](records.md) for who can see what you attach.
