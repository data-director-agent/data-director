# Vendored XML Schemas

The tests check a drafted OAI-DC record against the published OAI-DC XML Schema. The tests run
with the network blocked, so the schema and the two schemas it imports are kept here. Each file is
copied **unchanged**, byte for byte, as retrieved on 2026-11-24. The tests resolve each file's
import of the next through a local resolver, so no file is edited.

None of these files is covered by this library's MIT licence. Each stays under its publisher's
licence, as below.

| File | Source | SHA-256 | Licence |
|---|---|---|---|
| `oai_dc.xsd` | <http://www.openarchives.org/OAI/2.0/oai_dc.xsd>, the Open Archives Initiative, by Pete Johnston | `7383d21bca49c1186627e820a5da7ec209febfc5b4295fada39720ad0cebee9a` | [Creative Commons Attribution-ShareAlike 3.0 Unported](https://creativecommons.org/licenses/by-sa/3.0/), as stated at the foot of <https://www.openarchives.org/OAI/openarchivesprotocol.html> |
| `simpledc20021212.xsd` | <http://dublincore.org/schemas/xmls/simpledc20021212.xsd>, the Dublin Core™ Metadata Initiative, by Pete Johnston, Carl Lagoze, Andy Powell and Herbert Van de Sompel | `e9542e0cd08b59ad3ad994f50226dd7e6707792327b08f46eaa6250dd728d3aa` | [Creative Commons Attribution 4.0 International](https://creativecommons.org/licenses/by/4.0/), DCMI's [Schema Use Notice](https://www.dublincore.org/about/copyright/) |
| `xml.xsd` | <http://www.w3.org/2001/03/xml.xsd>, the World Wide Web Consortium | `0ed94db44402526e7a683424d0bd4b65e5bc50e65d9b9a762b11b30bae06d0c8` | [W3C Software and Document License](https://www.w3.org/copyright/software-license-2023/) |

## Notices

Portions of this software use XML schemas Copyright © 2002 [DCMI](https://www.dublincore.org/),
the Dublin Core™ Metadata Initiative. These are licensed under a
[Creative Commons Attribution 4.0 International License](https://creativecommons.org/licenses/by/4.0/).

`oai_dc.xsd`: the Open Archives Initiative Protocol for Metadata Harvesting, version 2.0. This
work is licensed under a
[Creative Commons Attribution-Share Alike 3.0 Unported License](https://creativecommons.org/licenses/by-sa/3.0/).

`xml.xsd`: <http://www.w3.org/2001/03/xml.xsd>. Copyright © 2001 World Wide Web Consortium. All
Rights Reserved. This work is distributed under the W3C® Software and Document License
(<https://www.w3.org/Consortium/Legal/copyright-software>) in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A
PARTICULAR PURPOSE.

### The W3C Software and Document License (2023), in full, for `xml.xsd`

Status: This document is in effect since 1 January 2023.

This work is being provided by the copyright holders under the following license.

**License.** By obtaining and/or copying this work, you (the licensee) agree that you have read,
understood, and will comply with the following terms and conditions.

Permission to copy, modify, and distribute this work, with or without modification, for any
purpose and without fee or royalty is hereby granted, provided that you include the following on
ALL copies of the work or portions thereof, including modifications:

- The full text of this NOTICE in a location viewable to users of the redistributed or
  derivative work.
- Any pre-existing intellectual property disclaimers, notices, or terms and conditions. If none
  exist, the W3C software and document short notice should be included.
- Notice of any changes or modifications, through a copyright statement on the new code or
  document such as "This software or document includes material copied from or derived from
  [title and URI of the W3C document]. Copyright © [$year-of-document] World Wide Web Consortium.
  https://www.w3.org/copyright/software-license-2023/"

**Disclaimers.** THIS WORK IS PROVIDED "AS IS," AND COPYRIGHT HOLDERS MAKE NO REPRESENTATIONS OR
WARRANTIES, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO, WARRANTIES OF MERCHANTABILITY OR
FITNESS FOR ANY PARTICULAR PURPOSE OR THAT THE USE OF THE SOFTWARE OR DOCUMENT WILL NOT INFRINGE
ANY THIRD PARTY PATENTS, COPYRIGHTS, TRADEMARKS OR OTHER RIGHTS.

COPYRIGHT HOLDERS WILL NOT BE LIABLE FOR ANY DIRECT, INDIRECT, SPECIAL OR CONSEQUENTIAL DAMAGES
ARISING OUT OF ANY USE OF THE SOFTWARE OR DOCUMENT.

The name and trademarks of copyright holders may NOT be used in advertising or publicity
pertaining to the work without specific, written prior permission. Title to copyright in this
work will at all times remain with copyright holders.

Source: <https://www.w3.org/copyright/software-license-2023/>
