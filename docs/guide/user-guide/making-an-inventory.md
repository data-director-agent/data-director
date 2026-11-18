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

## What Data Director cannot see

Because the inventory holds no contents, no agent can find a problem that is only inside a file.
It cannot see:

- names, telephone numbers, e-mail addresses or access codes written in notes or a diary;
- whether coordinates are precise enough to point to a person, private land or a protected
  species;
- licence terms written inside a file you were given, such as "internal use only";
- the conditions or end date of an agreement;
- instructions written into a file, which it would in any case not follow.

What it can do is mark the files whose **names** suggest one of these, so that you look at them.
The app marks them in the inventory, under **Files to look at**, and the File Archivist lists them
when it is run:

| Marked as | Because |
|---|---|
| May hold free text | A folder or file name such as `notes`, `fieldnotes`, `diary`, `interview`, `transcript` or `consent` |
| May hold locations | A column such as `lat`, `lon`, `easting`, `northing`, `gridref` or `location` |
| May be someone else's | A folder such as `reference`, `external`, `vendor` or `downloaded` |
| Terms or an agreement | A folder or file name such as `agreement`, `licence`, `permission` or `governance` |
| System file | `Thumbs.db`, `desktop.ini`, `.DS_Store`, or a name beginning `~$` |
| Empty | The file has no bytes |
| Exact copy | Another file has the same digest |

A mark is a prompt for you, not a finding and not a decision: the file may be fine. And a file
with no mark is not cleared. That nothing was marked does not mean the data hold no personal data,
sensitive locations or someone else's material. Before you deposit, read any free-text files
yourself, check locations and material from others, and talk to your data steward or ethics
contact about anything you are unsure of.

## Making one

<!-- making-an-inventory:summary -->

In the app, select **Make an inventory** under the message box on the conversation page. It offers
two ways: describing a folder in your browser, which needs nothing installed, and a command you
run in a terminal. Use the browser unless your data are somewhere it cannot reach, or the dataset
is very large (below).

### Describing a folder in your browser

**Make an inventory** begins with **Describe a folder in this browser**. Select **Choose a
folder…** and pick the folder that holds your dataset. Your browser reads the files and makes the
inventory itself, running the same `dd-inventory` code as the command. None of your files is sent
anywhere: the app attaches only the inventory, and only after you have checked it (below). You can
also drop the folder onto that part of the dialog.

This works in current versions of Chrome, Edge, Firefox and Safari. Chrome and Edge ask whether to
let the site **view** the files in the folder; allow it. Some other browsers ask whether to
**upload** the files instead. That is the browser's standard wording for choosing a folder:
nothing is uploaded.

Safari does not show a folder's hidden files (those whose names begin with `.`) to the page. The
inventory is otherwise the same, but it does not mention them, as one made in another browser or
with the command does.

The first time, your browser fetches the scanner (about 16 MB), so allow a little longer; after
that it keeps a copy. Describing a folder in the browser is slower than the command, by about
three times, and a browser uses a lot of memory on very large files. Use the command instead when:

- your data are on a server, a cluster or network storage that your browser cannot reach;
- the dataset is very large, with files of several gigabytes or more.

If the folder you choose holds a file of 4 GB or more, the browser says so before it starts, and
suggests the command. Your browser's memory grows while it reads a file that large, and if your
computer runs short it may close the page, and the app with it. You can still go on with
**Describe it here anyway**.

An inventory made in the browser says so: the version of the tool that made it ends in
`+pyodide`, followed by a version number.

If your organisation's Data Director does not offer this, **Make an inventory** shows only the
command.

### With the command

**Make an inventory** shows these steps for the computer you are using, with a button to copy each
command, and ends with a button to attach the file you made. The steps are the same here:

<!-- making-an-inventory:steps -->

If you prefer pip, install the command once with `pip install data-director-inventory`, then run
`data-director-inventory path/to/dataset -o inventory.json`. The package is published on
[PyPI](https://pypi.org/project/data-director-inventory/).

If neither way suits you, ask your research data support team, or whoever is running a workshop
you are in, to make the inventory for you.

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

If your files change, make a new inventory of the folder that changed and choose it under
**Update with a new scan**: say under **Scan of** which folder it is, then choose the file as
**New scan**. Only that folder is replaced. What you said about each file is carried over to the
new scan wherever the file is still there, and the app tells you which files are new, changed or
gone. One thing cannot be carried over: anything you left out before was never kept, so it
appears again in the new scan. Check the files marked **New in this scan** and leave them out
again if you need to.

### Data in more than one place

If your dataset is in several folders, perhaps on different computers or with different
colleagues, the project's inventory can be made of several folders. Make an inventory of each
folder where it is. Then, under **Update with a new scan**, choose **A folder the inventory does
not have yet**, give the folder a name, and choose its file. The first time, you also name the
folder the inventory already has. Each file is then listed under its folder's name, and each
folder can be updated later on its own, by whoever holds it. If the folders are on one computer,
you can make one inventory of them all at once by naming each folder to the command:
`uvx data-director-inventory raw processed -o inventory.json`.

See [What the Data Director records](records.md) for who can see what you attach.
