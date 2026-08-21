# SPDX-License-Identifier: GPL-3.0-or-later
"""General-purpose static reverse engineering of an IPA -- class-dump,
strings, symbols, security posture, and version diffing -- built on the same
Mach-O/ObjC analysis engine `ipa_forge.hooks` uses for hook verification
(`ipa_forge.machO.objc`). See `forge analysis --help`.

Deliberately out of scope, by design, not oversight (see ROADMAP.md):

- **FairPlay/App Store DRM decryption.** Every command here assumes an
  already-decrypted `.ipa`, exactly like the rest of ipa-forge; decryption
  is DRM-circumvention tooling, a different risk category from static
  analysis of a binary you already have rights to inspect.
- **Instruction-level disassembly/decompilation** (capstone/Ghidra-grade).
  A large additional dependency and maintenance surface; tracked as a
  future phase in ROADMAP.md rather than bundled by default.
"""

from __future__ import annotations
