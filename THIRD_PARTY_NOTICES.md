# Third-party notices

The Class A GPCR Atlas application ships one third-party file, `vendor/ngl.js`. That file is a
bundle: it contains NGL itself and several libraries NGL builds on, each under its own licence.
Every notice below is reproduced because the corresponding licence requires it.

This file covers **software only**. Data sources and their licences are listed separately in the
application's reference panel and in `reports/phase6a/DATA_DISTRIBUTION_MATRIX.csv`.

The licence of this project's own code and output is **not stated here because it is not yet
decided** — see `governance/DEFERRED_DECISIONS.md` DD-12.

---

## NGL Viewer 2.3.1

- Source: `https://unpkg.com/ngl@2.3.1/dist/ngl.js`
- Distributed file SHA-256: `0e8fea984b0e306d948d675f30e10f5a275ab5b4ce2135191a6787ec1b29dc5d`
- Verified byte-identical to the published npm distribution of `ngl@2.3.1`, retrieved
  2026-08-05 from `https://cdn.jsdelivr.net/npm/ngl@2.3.1/dist/ngl.js`.
- Licence text retrieved 2026-08-05 from
  `https://raw.githubusercontent.com/nglviewer/ngl/v2.3.1/LICENSE`
  (SHA-256 `72883774990bc4687d410aafac767cacea8a3eb78fe2c0c7f67d937f77db7add`).

```
The MIT License

Copyright (c) 2014-2017, Alexander S Rose

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.
```

## three.js (r158, bundled inside `ngl.js`)

NGL bundles three.js rather than loading it separately. The bundle identifies itself at runtime
as `three.js r158` (it sets `data-engine="three.js r158"` on the WebGL canvas), which is how the
version below was determined — it is observed from the shipped file, not assumed.

Licence text retrieved 2026-08-05 from `https://raw.githubusercontent.com/mrdoob/three.js/r158/LICENSE`
(SHA-256 `852e0e8699169bf9f6fdc6bda3e682d078dcbc738b5d33e74df594721bff271d`).

```
The MIT License

Copyright © 2010-2023 three.js authors

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.
```

## chroma.js (bundled inside `ngl.js`)

BSD 3-clause. The notice is carried inline in the bundle; the full text was also retrieved
2026-08-05 from `https://raw.githubusercontent.com/gka/chroma.js/master/LICENSE`
(SHA-256 `85aae6740628115550c6e67a85e8f8e70835cd5b14d4a2cb878c90c998f506db`) and is stored at
`data/licences/third_party/chroma.js.LICENSE.txt`.

The inline notice in the shipped bundle reads, verbatim:

```
chroma.js - JavaScript library for color conversions

Copyright (c) 2011-2017, Gregor Aisch
All rights reserved.

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are met:

1. Redistributions of source code must retain the above copyright notice, this
   list of conditions and the following disclaimer.

2. Redistributions in binary form must reproduce the above copyright notice,
   this list of conditions and the following disclaimer in the documentation
   and/or other materials provided with the distribution.

3. The name Gregor Aisch may not be used to endorse or promote products
   derived from this software without specific prior written permission.
```

Retrieved text at the URL above is the authority; the block above is what the shipped file
itself carries.

## ColorBrewer colour tables (bundled inside `chroma.js`, inside `ngl.js`)

```
ColorBrewer colors for chroma.js

Copyright (c) 2002 Cynthia Brewer, Mark Harrower, and The
Pennsylvania State University.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at
http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software distributed
under the License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR
CONDITIONS OF ANY KIND, either express or implied. See the License for the
specific language governing permissions and limitations under the License.
```

Apache License 2.0 full text retrieved 2026-08-05 from
`https://www.apache.org/licenses/LICENSE-2.0.txt`, stored at
`data/licences/third_party/Apache-2.0.LICENSE.txt`.

## JS Signals (bundled inside `ngl.js`)

The shipped bundle carries this notice inline, verbatim:

```
JS Signals <http://millermedeiros.github.com/js-signals/>
Released under the MIT license
Author: Miller Medeiros
Version: 1.0.0 - Build: 268 (2012/11/29 05:48 PM)
```

**A standalone licence file could not be retrieved.** `LICENSE`, `LICENSE.txt` and
`MIT-LICENSE.txt` at the project's repository root all returned HTTP 404 on 2026-08-05. The
inline notice above is therefore the only first-party licence statement this project has for
this component, and it is reproduced rather than substituted with a generic MIT text — writing
out a licence body the upstream project did not publish at the location checked would be
inventing a document. Resolving this is listed as an open item in
`reports/phase6a/THIRD_PARTY_NOTICE_AUDIT.md`.

## Kdtree (bundled inside `ngl.js`)

```
Kdtree
@author Alexander Rose <alexander.rose@weirdbyte.de>, 2016
@author Roman Bolzern <roman.bolzern@fhnw.ch>, 2013
@author I4DS http://www.fhnw.ch/i4ds, 2013
@license MIT License <http://www.opensource.org/licenses/mit-license.php>
```
