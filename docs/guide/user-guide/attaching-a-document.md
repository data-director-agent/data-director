# Attaching a document

Besides an [inventory](making-an-inventory.md), you can attach a document **about** your data
to a message: a sampling protocol, a codebook, a lab notebook page or a README you already have.
Data Director keeps it in your project.

## What to attach

- Plain text (`.txt`) or Markdown (`.md`) files, of at most 256 KB.
- Word documents (`.docx`) and PDFs, of at most 1 MB, such as a data management plan exported
  from DMPonline, DMPTool or DSW. Data Director reads their text inside your institution's
  deployment and keeps the file beside it. A scanned PDF that holds only images of pages cannot
  be read: export the document again with its text, or save it as a Word or text file.
- Documents that describe how the data were made, what the variables mean or how the files are
  organised.

Never attach the data themselves, such as a CSV of measurements or interview transcripts, and
never attach anything that identifies a person. Data Director cannot tell a document from data,
so it relies on you to keep to this rule. To describe your data files, make an inventory instead.

## Attaching it in the app

On the conversation page, select **Attach a file** under the message box, or beside the Data
Director's questions while it is asking some, and choose the
document, or drop it onto the message box. The app shows you the document's name, size and text
before anything is kept, and what a check of its text found under **Possible personal data or
secrets**: e-mail addresses, telephone numbers, NHS or National Insurance numbers, postcodes,
keys, tokens or passwords. It says what kind of thing it found and how sure it is, never what
it found. Remove what it lists from the file and choose the file again, or, if it should be kept,
such as a public contact address, tick that you have checked the document and select **Attach
anyway**. Finding nothing does not mean there is nothing: names and places are not looked for.
When you are content, select **Attach this document**. If you select **Cancel**, nothing is
attached.

You can also attach a document without starting a conversation. On the project's **Documents**
page, select **Attach a document** and choose the file. It goes through the same check, and
selecting **Attach this document** keeps it in the project straight away. The documents the
project holds are listed under **Attached documents**. Where your institution does not allow
attached documents, the button is not offered.

The document then shows as a chip under the message box. Select its **Remove** button if you
change your mind. You can type a message as well, or send it on its own. A message can carry one
inventory and one document.

Attach files one at a time. If you choose or drop several together, the app opens the first and
tells you, under the message box, which of the others were not attached; attach each of those on
its own. If you attach a document while another is already attached, the new one replaces it:
the app says so before you attach it, so you can select **Cancel** to keep the first.

## Where it goes

The document is stored in your project, and anyone working on the project can read it.

When Data Director drafts a README or a data dictionary, the Documentation Editor reads the text
of the documents you attached, the latest first. Its AI model may then suggest answers to the
draft's questions from them, such as a field's unit that your field notes give, or how the
data were collected for the README's Methods section. Methods is suggested only from your
documents, never guessed from your files. A suggestion is
shown beside its question and is never written into the draft: it becomes part of the document
only when you save it, or a correction of it, as your answer. The outcome of the draft names the
documents the model was given, and says if one was too long to give in full.

The Data Management Plan Checker reads an attached data management plan to find its commitments
to share your data, which you then confirm or correct.

The Policy Adviser reads an attached policy or award letter as the text of the policy of the
funder, journal or institution it names, beside the published policies it finds. Each obligation
it reports quotes the passage it comes from, and cites the document by name, for you to confirm.
A document that names none of them is read for the only one you gave; if you gave several, it is
not read, and the adviser says so.

The agent you are talking to, and every other agent, is told only each document's name, type and
size, and cannot use its text. Before you attach a
document, the app names the agents in your deployment that read its text. The text goes to an AI model hosted outside your institution only if your institution's
deployment allows that; where it does not, drafts are made without it.

Your institution may choose not to keep attached documents at all. Then **Attach a file** takes
only an inventory, the note beneath it says that documents are not kept, and no agent is given a
document your project already holds. Give what the document says in your message instead.
