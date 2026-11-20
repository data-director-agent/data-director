# Depositing your data

The Data Director gets your project ready to deposit. Once it has built the deposit package, you
publish your data in the repository you chose, using the metadata you approved. Where the
deployment can, it first creates a **draft** in the repository for you, with your own account
there ([Depositing a draft to Zenodo](#depositing-a-draft-to-zenodo)); otherwise you create the item
by hand. This page explains both.

Data Director does not publish, register a DOI, upload your data files or release an embargo. The
repository does those when you publish the item there. Depositing a draft to Figshare (ORDA) is
planned (TODO(#383)).

## Before you start

In the project's **Deposit** tab:

1. Choose **Check the project**. The project is checked against what the repository you chose
   asks for. Anything listed under *Must be fixed before packaging* stops the package; fix it and
   check again.
2. Under *Decide before packaging*, decide each file the check lists. A file is listed when its
   name suggests something a person should look at before it is shared, such as field notes,
   coordinates, material from someone else or an agreement, or when the inventory command found
   possible personal data in it. For each, say whether you checked it and will deposit it as it
   is, will leave it out, or will deposit a changed copy, such as a redacted one; you may add a
   note. Data Director does not change your files: leaving a file out or changing it is up to you
   when you deposit.
3. Confirm that the ethics approvals that apply are in place, that data protection advice has
   been taken where the data concern living people, and that you may share any material from
   others. Your decisions and your confirmation are kept with your name and the time, and go into
   the package. A file that is not listed has not been cleared: the check reads names, not
   contents, and says what it did not look at.
4. Choose **Build the package**, then **Download the package**. It can be built once nothing must
   be fixed and nothing waits for your decision.

The **Repository** tab shows the repository you chose and the fields its form asks for.

## What the package is for

The package is the record of how your dataset was prepared. It holds:

- the documents you approved, including the metadata record;
- the record of who decided what, and when;
- how generative AI was used, and a disclosure statement;
- a list of your data files, each with its size and SHA-256 digest (a fingerprint).

Your data files are listed but not included. The package is not a file the repository reads or
imports: keep it with the project, and attach it to the item if the repository lets you and you
want it published alongside your data.

## Steps in the repository

The **Deposit** tab lists these steps once the package is built, with the details for the
repository you chose.

1. **Create the item.** Sign in to the repository and start a new item (a dataset, or the item
   type your data is).
2. **Enter the metadata.** Open the approved metadata record (in the package under `documents/`,
   or in the project's **Documents** tab) and copy each value into the repository's form. Where
   the deployment knows the repository's form, the Deposit tab names the form's fields, such as
   *Title*, *Authors* and *Keywords*, required ones first. A value the profile names no form field
   for can go wherever the form allows, or stay in the record.
3. **Attach your data files.** Upload the files the package lists. Their digests in the package
   show that the files you upload are the files that were described.
4. **Keep the package.** Store it with the project's records, or attach it to the item.
5. **Review and publish.** Check the item's preview, set any access restriction or embargo the
   repository offers, and publish it. The repository registers the DOI.

## Depositing a draft to Zenodo

Where the deployment deposits to Zenodo for you, the **Deposit** tab shows *Deposit a draft to
Zenodo* once the package is built.

1. **Connect your Zenodo account, once.** On the **Settings** page, open *Repository accounts*.
   Choose *Connect your Zenodo sandbox account*, sign in at Zenodo, and approve. Data Director asks
   only to create drafts, never to publish. If the deployment offers no sign-in, create a personal
   token in Zenodo under *Applications*, with only the `deposit:write` scope, and paste it there
   instead. Your account is kept encrypted by the deployment's deposit broker; the rest of Data
   Director never sees it, and you can disconnect it at any time.
2. **Approve the deposit.** On the **Deposit** tab, choose *Create a draft in Zenodo*. Your choice
   is recorded with your name and the time. Data Director creates a draft holding the approved
   metadata and the package, and links to it. It names any part of the metadata record Zenodo's
   form has no place for, such as funding, which you can add in Zenodo.
3. **Finish in Zenodo.** Open the draft, upload your data files, check it, and publish it, or
   delete it. Data Director does neither.

If no draft is made, the tab says why: most often, that your account is not connected yet. Nothing
is published either way, and you can try again.

### Practising on a test deployment

A test deployment, such as the alpha server, deposits to the **Zenodo sandbox**,
`sandbox.zenodo.org`, and says so beside the deposit. The sandbox is a test copy of Zenodo: its
records and DOIs are not real, and it is emptied from time to time. It needs its own account,
separate from any account on `zenodo.org`; create one at `sandbox.zenodo.org` before you connect it.
You can publish a sandbox draft to see what happens, without making a real record.

## ORDA

ORDA, the University of Sheffield's repository, runs on Figshare. The form labels the Deposit tab
shows for ORDA come from the deployment's profile of it, not from the app, so a steward can
correct them without a new release.

Some of what ORDA asks is not yet confirmed. The Deposit tab lists those items under *Not yet
confirmed for ORDA*; until they are settled, follow ORDA's own deposit form where it differs
(TODO(#385)).

## See also

- [The workflow](workflow.md), Phase 5: Deposit and submit
- [What the Data Director records](records.md)
