# Ligand Paneli — Uygulama Belgesi

**Class A GPCR Atlas · ölçülmüş kapsam, veri modeli ve devredilebilir teknik plan**

Hazırlanma tarihi: **9 Ağustos 2026**
Çalışma kökü: `/media/arma/Elements/python_projeler/pymol_views/class_a_gpcr_atlas`
Kaynak araştırma: `../Class_A_GPCR_Ligand_Explorer_Research_and_Specification_2026-08-09.md`

Bu belgedeki **her sayı bu korpusta ölçülmüştür**; hiçbiri araştırma raporundan
devralınmamış veya tahmin edilmemiştir. Ölçüm betiklerinin çıktıları
`/tmp/claude-1000/ligand_audit.txt` ve `/tmp/claude-1000/smarts_validation.txt`
içinde; §9'da kalıcı hâle getirilmeleri planlanmıştır.

Uygulamaya **henüz başlanmamıştır.** Belge sonundaki STOP POINT kabul edilmeden kod yazılmaz.

---

## 1. Ölçülmüş korpus auditi

### 1.1 Yapı düzeyi

| Ölçüt | Pay / Payda | Oran |
|---|---|---|
| Toplam Class A yapısı | 1358 | — |
| Farmakolojik ligand bulunan yapı | 1230 / 1358 | **%90,6** |
| Çoklu farmakolojik ligand içeren yapı | 48 / 1230 | %3,9 |
| Manuel inceleme gereken yapı | 54 / 1358 | %4,0 |

Ligandsız 128 yapı: doğrulanmış apo (82), apo durumu çözülmemiş (46) — bunlar
§1.5'teki cep ayrıntısı boşluk kategorileriyle aynı kümedir.

### 1.2 Yapı–ligand örneği (instance) düzeyi

| Ölçüt | Pay / Payda | Oran |
|---|---|---|
| Toplam ligand adayı kaydı | 1331 | — |
| Farmakolojik olarak ilgili instance | 1281 / 1331 | %96,2 |
| Farmakolojik olmayan bileşen | 50 / 1331 | %3,8 |

İlgili instance'ların `entity_form` dağılımı:

| entity_form | Sayı | Oran |
|---|---|---|
| `nonpolymer_residue` | 942 / 1281 | %73,5 |
| `polymer_chain` | 294 / 1281 | %23,0 |
| `covalent_adduct` | 45 / 1281 | %3,5 |

`biological_type` dağılımı:

| biological_type | Sayı | Oran |
|---|---|---|
| `small_molecule` | 979 / 1281 | %76,4 |
| `peptide` | 232 / 1281 | %18,1 |
| `protein` | 63 / 1281 | %4,9 |
| `lipid` | 7 / 1281 | %0,5 |

### 1.3 Kimya zenginleştirme kapsaması — **belgenin en önemli tablosu**

| Ölçüt | Pay / Payda | Oran |
|---|---|---|
| CCD taşıyan instance (kimya uygulanabilir) | 987 / 1281 | %77,0 |
| CCD taşımayan instance (peptit/polimer) | 294 / 1281 | %23,0 |
| **RDKit ile zenginleştirilebilir instance** | **985 / 1281** | **%76,9** |
| Parse başarısız instance | 2 / 1281 | %0,2 |

### 1.4 Benzersiz form ve kavram düzeyi

| Ölçüt | Pay / Payda | Oran |
|---|---|---|
| Farmakolojik instance'larda benzersiz CCD | 493 | — |
| bunlardan RDKit ayrıştırdı | 492 / 493 | %99,8 |
| Önbellekteki tüm CCD | 580 | — |
| RDKit ayrıştırdı | 579 / 580 | %99,8 |
| Standardize kimyasal kavram (connectivity InChIKey) | 557 / 579 | %96,2 |

> **İki oranı asla tek sayıya indirgemeyin.**
> Benzersiz CCD kapsaması **%99,8**, structure–ligand instance kapsaması **%76,9**.
> Aradaki 23 puan peptit ve polimer ligandlardır; onların CCD'si yoktur, dolayısıyla
> CCD tabanlı kimya katmanı onlara uygulanamaz.
>
> Ters yönde de yanıltıcıdır: tek bir CCD çok sayıda yapıda bulunabilir. Korpusta
> `G1I` **81** instance'ta, `RET` (retinal) **41**, `ZMA` **31** kez geçiyor. Benzersiz
> ligand sayısıyla yapılan bir kapsama iddiası bu ağırlığı görmez.

### 1.5 Belirsizlik ve inceleme kuyruğu

| Ölçüt | Pay / Payda | Oran |
|---|---|---|
| `analysis_eligibility = unresolved_manual_review` | 75 / 1331 | %5,6 |
| `manual_review_status = required` | 66 / 1331 | %5,0 |

### 1.6 Parse başarısızlığı

Tek vaka: **`WJS`** — bir lizofosfatidik asit türevi. Çökeltilmiş SMILES'ı standart dışı
valans gösterimi kullanıyor (`[C]`, `[NH3]`, `$l^{6}-phosphanyl`). RDKit'in değil kaydın
sorunudur.

**Kural:** boru hattı durmaz, molekül elle düzeltilmez. Kayıt şu biçimde tutulur:

```json
{
  "ccd": "WJS",
  "parse_status": "failed",
  "parse_error": "non-standard valence representation",
  "raw_smiles": "<çökeltilmiş SMILES aynen korunur>",
  "descriptors": null,
  "facets": {}
}
```

İleride alternatif bir gösterim (PubChem/ChEMBL) denenebilir; ancak sessizce
düzeltilmiş bir molekül **kullanılmaz**.

---

## 2. Paydaların açık tanımı

Bu tanımlar veri modelinde ve arayüzde birebir kullanılır; oranlar bunlar dışında
raporlanmaz.

| Ad | Tanım | Değer |
|---|---|---|
| `structures_total` | Atlastaki tüm Class A PDB yapısı | 1358 |
| `structures_with_pharmacological_ligand` | En az bir `pharmacological_relevance=relevant` adayı olan yapı | 1230 |
| `ligand_candidates_total` | `ligand_candidates.jsonl` kayıt sayısı | 1331 |
| `instances_relevant` | Farmakolojik olarak ilgili yapı–ligand örneği | 1281 |
| `instances_with_ccd` | CCD'si olan ilgili instance (kimya uygulanabilir) | 987 |
| `instances_chemistry_enriched` | Kimya kaydı üretilen ilgili instance | 985 |
| `unique_ccd_relevant` | İlgili instance'larda geçen benzersiz CCD | 493 |
| `unique_ccd_cached` | Önbellekteki tüm CCD | 580 |
| `chemical_concepts` | Benzersiz connectivity InChIKey (ilk blok) | 557 |

**Arayüz kuralı:** bir kimya filtresi etkinken sonuç sayacı hem eşleşen instance'ı hem de
**kimyası olmayan** instance sayısını göstermek zorundadır. "294 yapı–ligand örneğinin
kimyası yok" bilgisi gizlenirse kullanıcı %77'lik bir alt kümeyi bütün sanır.

---

## 3. Üç katmanlı JSON veri modeli

İlişkisel veritabanına geçilmez. Araştırma raporunun ~20 tablosu **uygulanmaz**; onun
yerine üç kavramsal katman mevcut statik JSON mimarisinde korunur:

```
chemical concept  (connectivity InChIKey — stereo/tuz/tautomer bağımsız iskelet)
      └── exact ligand form / CCD  (tam InChIKey, stereo dahil)
              └── PDB structure–ligand instance  (pdb_id + ligand_entity_id)
```

Katmanların nerede yaşadığı:

| Katman | Dosya | Not |
|---|---|---|
| chemical concept | `ligand_chemistry.json` içinde `concept_key` alanı | ayrı dosya değil, alan |
| exact form / CCD | **`data/web/global/ligand_chemistry.json`** (yeni) | CCD başına tek kayıt |
| PDB instance | mevcut `families/<slug>/structures.json` → `observations[]` | **şema değişmez**, yalnız `ccd` referansı zaten var |

Ek dosyalar:

| Dosya | İçerik |
|---|---|
| `data/web/global/chemistry_catalog.json` | 39 SMARTS tanımı, TR/EN etiket, kategori, parent, facet hiyerarşisi |
| `data/web/global/ligand_chemistry_audit.json` | Parse başarısı, hata nedeni, RDKit sürümü, §1'deki tüm pay/payda |

**Kritik tasarım kararı:** kimya CCD düzeyinde saklanır, instance düzeyinde **tekrarlanmaz**.
`G1I` 81 yapıda geçiyor; descriptor'ları 81 kez yazmak hem 80 kat şişme hem de tutarsızlık
riski demektir. Arayüz `observation.ligand_components[0]` → `ligand_chemistry[ccd]`
araması yapar.

### Örnek kayıt (gerçek çıktı, prototipten)

```json
{
  "ccd": "ALE",
  "parse_status": "ok",
  "name": "L-EPINEPHRINE",
  "inchikey": "UCTWMZQNUQWSLP-VIFPVBQESA-N",
  "concept_key": "UCTWMZQNUQWSLP",
  "descriptors": {
    "mw": 183.21, "exact_mass": 183.0895, "mollogp": 0.35, "tpsa": 72.72,
    "hbd": 4, "hba": 4, "rotb": 3, "heavy_atoms": 13,
    "formal_charge": 0, "aromatic_rings": 1, "fraction_csp3": 0.333
  },
  "facets": {
    "functional_groups": ["fg_alcohol", "fg_catechol", "fg_phenol", "fg_secondary_amine"],
    "ring_systems": ["rs_phenyl"],
    "scaffolds": ["chemo_catecholamine"]
  },
  "provenance": {
    "smiles_source": "RCSB chem_comp SMILES_CANONICAL (CACTVS)",
    "computed_by": "RDKit 2025.09.6",
    "catalog_version": "1.0.0"
  }
}
```

Adrenalin için katekol + fenol + sekonder amin + alkol, tek fenil halkası — bilimsel
olarak doğru.

---

## 4. Kimya zenginleştirme alanları

### 4.1 MVP descriptor seti (hepsi RDKit ile yeniden hesaplanır)

| Alan | RDKit çağrısı | Birim | UI filtresi |
|---|---|---|---|
| `mw` | `Descriptors.MolWt` | Da | aralık kaydırıcısı |
| `exact_mass` | `Descriptors.ExactMolWt` | Da | gizli (dışa aktarımda) |
| `mollogp` | `Crippen.MolLogP` | — | aralık kaydırıcısı |
| `tpsa` | `rdMolDescriptors.CalcTPSA` | Å² | aralık kaydırıcısı |
| `hbd` / `hba` | `CalcNumHBD` / `CalcNumHBA` | adet | aralık |
| `rotb` | `CalcNumRotatableBonds` | adet | aralık |
| `heavy_atoms` | `GetNumHeavyAtoms` | adet | aralık |
| `formal_charge` | `Chem.GetFormalCharge` | e | kategorik (−, 0, +) |
| `aromatic_rings` | `CalcNumAromaticRings` | adet | aralık |
| `fraction_csp3` | `CalcFractionCSP3` | 0–1 | aralık |

**Provenance kuralı:** bu değerler *hesaplanmıştır*, kaynaktan gelmemiştir. Kaynak
(PubChem/ChEMBL) değerleri **karıştırılmaz**; istenirse ayrı `property_observation`
alanında, kaynağıyla birlikte saklanır. Arayüzde "RDKit 2025.09.6 ile hesaplandı" ibaresi
görünür.

**`logD₇.₄` kapsam dışıdır.** RDKit güvenilir pKa/logD sağlamaz; hesaplanmış bir değeri
deneysel gibi sunmak yanlış olur.

### 4.2 Üç ayrı facet

Karıştırılmaz, üç ayrı alan:

| Facet | Ne | Korpusta |
|---|---|---|
| `functional_groups` | Fonksiyonel grup (amid, amin, karboksilat…) | 26 desen |
| `ring_systems` | Halka sistemi (indol, piridin, ksantin…) | 13 desen |
| `scaffolds` | GPCR chemotype (katekolamin, triptamin, ariloksipropanolamin…) | **MVP'de yok**, Aşama 3 |

---

## 5. SMARTS semantik doğrulaması

Araştırma raporunun 39 deseni belgeden çıkarılıp **bu korpusta** doğrulandı.

### 5.1 Sözdizimi ve ayrım testleri

| Test | Sonuç |
|---|---|
| Sözdizimi geçerli | **39 / 39** |
| Pozitif örnek testleri | **8 / 8** geçti |
| Negatif ayrım testleri | **6 / 6** geçti |

Negatif ayrımlar (raporun iddia ettiği, bizim doğruladığımız):

- asetamid ↛ birincil amin ✅
- N,N-dimetilasetamid ↛ tersiyer amin ✅
- metansülfonamid ↛ sekonder amin ✅
- metil asetat ↛ eter ✅
- fenol ↛ alifatik alkol ✅
- etanol ↛ fenol ✅

### 5.2 Üst–alt (parent–child) tutarlılığı

Alt kümenin üst kümeye dahil olması korpusta test edildi — **8 / 8 tutarlı**:

`catechol ⊆ phenol` · `urea ⊆ amide` · `guanidine ⊆ amidine` ·
`ester / ketone / aldehyde / amide / carboxylic_acid ⊆ carbonyl`

### 5.3 Korpus düzeyi eşleşmeler (iki düzey ayrı)

| Grup | Benzersiz ligand | Structure-instance |
|---|---:|---:|
| `rs_phenyl` | 417 | 720 |
| `fg_carbonyl` | 396 | 549 |
| `fg_ether` | 221 | 348 |
| `fg_amide` | 221 | 307 |
| `fg_carboxylic_acid` | 159 | 160 |
| `fg_tertiary_amine` | 150 | 214 |
| `fg_alcohol` | 141 | 340 |
| `fg_primary_amine` | 134 | 179 |
| `fg_secondary_amine` | 110 | 284 |
| `rs_indole` | 49 | 96 |
| `fg_catechol` | 16 | **124** |
| `rs_tetrazole` | 8 | 10 |
| `fg_sulfonic_acid` | 1 | **0** |

Son iki satır neden önemli:

- **`fg_catechol` 16 ligand → 124 instance.** Katekolaminler az sayıda moleküldür ama çok
  yapıda çözülmüştür. İki düzeyi ayırmazsak "16 ligand" küçük görünür, oysa atlasın
  önemli bir kısmını kapsar.
- **`fg_sulfonic_acid` 1 ligand → 0 instance.** O ligand önbellekte var ama hiçbir yapıda
  farmakolojik ligand olarak seçilmemiş. Instance sayacı bunu doğru gösteriyor; benzersiz
  sayaç yanıltırdı.

### 5.4 Semantik doğrulama örneği

`fg_catechol` eşleşmeleri elle incelendi: **ALE** (adrenalin), **E5E** (noradrenalin),
**LDP** (dopamin), **5FW** (izoprenalin), **Y00** (dobutamin), **OR9** (apomorfin benzeri),
SK0/SK9/GBU (D1 benzazepinleri), G1I/GJ6 (aminotetralinler). Ders kitabı katekolamin
listesi — desen doğru çalışıyor.

**Kalan 38 desen için aynı gözle inceleme Aşama 1'in kabul koşuludur** (§8).

---

## 6. Arayüz facet tasarımı

Mevcut gezgin (`structures()`) korunur; ligand filtreleri **mevcut filtre ızgarasına**
eklenir, yeni bir sayfa açılmaz. Panel gezgininde de aynı kod çalışır.

### 6.1 Varsayılan görünür

| Filtre | Tip | Kaynak |
|---|---|---|
| Ligand sınıfı (Agonist/Antagonist…) | açılır | **mevcut**, değişmiyor |
| Biyolojik tip (küçük molekül / peptit / protein / lipid) | açılır | `biological_type` |
| Fonksiyonel grup | çoklu seçim | `facets.functional_groups` |
| Halka sistemi | çoklu seçim | `facets.ring_systems` |
| Molekül ağırlığı | aralık | `descriptors.mw` |
| logP (hesaplanmış) | aralık | `descriptors.mollogp` |

### 6.2 Gelişmiş (katlanır)

TPSA, HBD, HBA, döndürülebilir bağ, ağır atom, formal yük, aromatik halka, Fsp³.

### 6.2b Uygulanan üç durumlu mantık *(Aşama 2)*

Kimya filtresi boolean değil, üç durumlu:

| Durum | Anlamı | Arayüzde |
|---|---|---|
| `MATCH` | Kimya verisi var **ve** aktif filtrelerin hepsini karşılıyor | Ana listede ve ana sayaçta |
| `NO_MATCH` | Kimya verisi var, en az bir filtreyi karşılamıyor | Gösterilmiyor |
| `UNKNOWN` | Kimya verisi yok — filtre uygulanamıyor | Ayrı, başlangıçta kapalı bölümde |

Yapı düzeyine yuvarlama: en az bir ligand karşılıyorsa yapı `MATCH`; hiçbiri karşılamıyor
ama en az biri değerlendirilemiyorsa `UNKNOWN`; hepsi değerlendirildi ve hiçbiri
karşılamıyorsa `NO_MATCH`.

**Biyolojik tip ekseni ayrı çalışır.** Peptitlerin `biological_type` alanı vardır, bu yüzden
`Biyolojik tip = peptide` seçildiğinde peptitler gerçek `MATCH` olur. Aynı peptitler bir
fonksiyonel grup veya descriptor filtresi eklendiğinde `UNKNOWN`'a düşer.

Doğrulanmış örnek (peptit reseptörleri ailesi, 356 yapı, `tersiyer amin` filtresi):

```
MATCH      54 yapı  ·  54 doğrulanmış ligand eşleşmesi
UNKNOWN   228 yapı  ·  229 ligand örneği
             227 peptit / polimer — kimyasal bileşen kodu yok
               2 kimyasal gösterim bulunamadı
NO_MATCH   74 yapı  (gösterilmiyor)
────────────────────────────────────
toplam    356 = ailenin tamamı
```

Sayaçlar yapı ile ligand örneğini karıştırmaz: `Biyolojik tip = peptide` filtresinde
"191 sonuç · 192 doğrulanmış ligand eşleşmesi" çıkar — bir yapıda iki eşleşen peptit vardır.

Her descriptor kendi gerçek kapsamını gösterir (`{covered}/{total} ligand örneğinde var`);
genel %76,9 oranı hiçbir descriptor'a otomatik uygulanmaz.

### 6.3 Zorunlu dürüstlük kuralları

1. **Kimyası olmayan instance sayacı her zaman görünür.** Örnek: *"412 sonuç · 118 yapı–ligand
   örneğinin kimya verisi yok (peptit/polimer)"*.
2. Kimya filtresi etkinken peptit/polimer instance'lar **sessizce elenmez**; ayrı sayılır.
3. Her descriptor'ın yanında hesaplandığı belirtilir (RDKit sürümü, kaynak SMILES).
4. `parse_status=failed` ligandlar listede kalır, kimya alanları "hesaplanamadı" olarak görünür.
5. Farmakoloji rolü **molekülün değil gözlemin** özelliğidir; arayüz metni bunu yansıtır.

### 6.4 Kapsam ibaresi

Yöntemler ve ligand paneli başlığında sabit metin:

> Farmakolojik roller ağırlıkla GPCRdb kaynaklı, yapıyla ilişkilendirilmiş anotasyonlardır.
> Assay düzeyinde etkinlik ve niceliksel bias verisi bu sürümde temsil edilmemektedir.

---

## 7. Build ve performans etkisi

### 7.1 Ölçülmüş boyutlar (prototip üretildi)

| Dosya | Prototip tahmini | **Gerçekleşen** | Ne zaman yüklenir |
|---|---|---|---|
| `ligand_chemistry.json` | 255,8 KB | **381,6 KB** | ligand filtresi ilk kullanıldığında |
| `chemistry_catalog.json` | 6,3 KB | **9,1 KB** | ligand filtresiyle birlikte |
| `ligand_chemistry_audit.json` | ~30 KB | **1,5 KB** | yalnız Yöntemler sayfasında |

**Toplam artış 392,2 KB** (tahmin 292 KB). Mevcut site 501 MB → **%0,08 büyüme.**

Prototipten büyük olmasının sebebi, üretim kaydına eklenen alanlar: `raw_smiles` (parse
başarısızlığında da korunuyor), `name`, `component_type`, `free_form_status` ve
`pharmacological_instances`. Bunların hepsi provenans veya dürüstlük gereği; boyut karşılığında
alınmış bilinçli bir karar.

### 7.2 İlk açılış etkisi: +472 bayt

Landing ilk yükü 13.539 → **14.011 bayt**. `landing.json` **değişmedi** (6.855 bayt);
artışın tamamı `manifest.json`'da, çünkü bütünlük denetimi için üç yeni dosyanın
checksum'ı listeleniyor. Kimya dosyalarının kendisi landing'de yüklenmiyor.

### 7.3 Build süresi

RDKit ile 580 molekül × 39 SMARTS ≈ 22.620 alt yapı eşleştirmesi. Prototip ölçümünde
tamamı saniyeler sürüyor. Ağ isteği yok — SMILES yerel önbellekten geliyor.

### 7.4 Tarayıcı filtreleme

580 kayıtlık bir `Map` üzerinde arama; mevcut filtreler zaten 1358 kayıt üzerinde
çalışıyor. Ölçülebilir bir yavaşlama beklenmiyor, yine de §8'de kabul kriteri var.

---

## 8. Test ve kabul kriterleri

### 8.1 Bozulmama garantileri

- [ ] Mevcut **113 Phase 5 kontrolü** bozulmadan geçer.
- [ ] **37.407 temas kaydı** bit düzeyinde değişmez (checksum karşılaştırması).
- [ ] Mevcut farmakoloji sınıfı dağılımı değişmez (Agonist 293, Antagonist 61, …).
- [ ] Panel yapı sayıları değişmez (Gs 245, Gi/o 425, β-arrestin 20, …).
- [ ] Kimya alanları **yokken** de yapı sayfaları çalışır (dosya silinip test edilir).

### 8.2 Yeni kontroller

- [ ] `ligand_chemistry.json` JSON şemasına uyar.
- [ ] Enrichment **deterministik**: iki çalıştırma bayt düzeyinde aynı çıktı.
- [ ] `WJS` kontrollü `parse_failed`; ham SMILES korunmuş; descriptor `null`.
- [ ] 39 desenin **hepsi** için pozitif + negatif örnek testi.
- [ ] Parent–child tutarlılığı (8 ilişki) korpusta doğrulanır.
- [ ] Kapsam sayıları (§1) audit dosyasına yazılır ve testle karşılaştırılır.
- [ ] Yeni payload boyutları ölçülüp raporlanır; eşiği aşarsa test kırılır.
- [ ] Tarayıcı: ligand filtresi açılış süresi ve filtreleme gecikmesi ölçülür.
- [ ] Provenance alanları (RDKit sürümü, SMILES kaynağı, katalog sürümü) dolu.

### 8.3 Offline ve cache

- [ ] Normal build **hiçbir harici API'ye** bağlanmaz (ağ kapalıyken tam derleme testi).
- [ ] GtoPdb önbellek girdileri retrieval date + checksum ile dondurulur.
- [ ] `--refresh` ayrı, açıkça çağrılan bir işlemdir; varsayılan akışta yer almaz.

---

## 9. Aşamalı uygulama sırası

### Aşama 0 — ölçümleri kalıcı hâle getir *(yarım gün)*

`pipeline/enrichment/audit_ligand_chemistry.py`: §1'deki tüm pay/payda değerlerini
`reports/enrichment_ligand_audit.md` ve `ligand_chemistry_audit.json` olarak üretir.
**Bu aşama kod değil ölçüm üretir**; sonraki aşamaların kabul zemini olur.

Ayrıca `data/cache/gtopdb/` girdilerine retrieval date + checksum manifesti eklenir.

### Aşama 1 — kimya katmanı *(1–2 gün)*

`pipeline/enrichment/build_ligand_chemistry.py`
→ `data/web/global/ligand_chemistry.json` + `chemistry_catalog.json`

- SMILES → RDKit → descriptor + facet
- `config/enrichment/chemistry_catalog.json` (39 desen, TR/EN etiket, parent)
- 39 desen için pozitif/negatif test dosyası
- `schemas/enrichment/ligand_chemistry.schema.json`
- `build_payloads.py` yeni global dosyaları manifest'e kaydeder

### Aşama 2 — arayüz *(1–2 gün)*

`loader.js` (yeni yükleyici), `views.js` (filtreler + kimya bölümü), `i18n.js` (TR/EN),
`atlas.css`. §6.3'teki beş dürüstlük kuralı uygulanır.

### Aşama 3 — chemotype/scaffold *(ayrı karar)*

Bemis–Murcko + elle tanımlı GPCR chemotype'ları. **Bu aşama ayrı onay ister**; hangi
chemotype listesinin kullanılacağı bilimsel bir karardır ve bu belgede çözülmemiştir.

### Kapsam dışı (bu sürümde yapılmayacak)

`assay` · `activity_measurement` · `quantitative bias` · `reference ligand` ·
`transduction coefficient` · `logD₇.₄` · substructure çizim/arama · chemical-space
görselleştirme · contact enrichment istatistiği

Bunlar için **boş alan açılmaz**. Elimizde veri yok; varmış gibi göstermek yanlış olur.
22 satırlık kürasyonlu kanıt mevcut `pathway_evidence` katmanında kalır, kimya modeline
karıştırılmaz.

---

## 10. Riskler ve çözülmemiş sorunlar

| Risk | Etki | Önlem |
|---|---|---|
| **%23 instance kimyasız** | Kullanıcı %77'lik alt kümeyi bütün sanar | §6.3 kural 1: sayaç her zaman görünür |
| Aynı CCD çok yapıda | Kapsama oranı şişer | İki düzey ayrı raporlanır (§1.3–1.4) |
| GtoPdb API anahtarı (Ağu 2026 sonu) | `--refresh` kırılır | Önbellek dondurulur; normal build offline |
| RDKit sürüm kayması | Descriptor değerleri değişir | Sürüm pinlenir + provenance'ta yazılır |
| SMARTS tautomer/protonasyon kaçırması | Sessiz eksik eşleşme | Katalog sürümlenir; 39 desen gözle incelenir |
| Peptit ligandlar için kimya yok | Filtre onları eleyebilir | Ayrı `biological_type` filtresi; sessiz eleme yasak |
| Prototip = üretim sanılması | Ölçümler yanlış devredilir | Aşama 0 ölçümleri kalıcı üretir |

**Çözülmemiş, karar bekleyen:**

1. **Chemotype listesi** — hangi GPCR scaffold'ları, hangi kaynağa dayanarak? (Aşama 3)
2. **Peptit ligandlar için alternatif descriptor** — uzunluk, disülfit sayısı, net yük
   hesaplanabilir; MVP'ye dahil mi?
3. **`covalent_adduct` (45 instance)** — kovalent ligandın kimyası bağlanmamış hâliyle mi
   temsil edilecek?

---

# STOP POINT

## Ölçülen kapsam

```
Yapı                1358 toplam · 1230 farmakolojik ligandlı (%90,6)
Instance            1331 aday · 1281 ilgili (%96,2)
Kimya uygulanabilir  987 / 1281 instance (%77,0)
RDKit zenginleştirdi 985 / 1281 instance (%76,9)   <-- gerçek kapsam
Benzersiz CCD        492 / 493 ayrıştı (%99,8)      <-- yanıltıcı olan
Kimyasız             294 / 1281 (%23,0) peptit/polimer
Parse başarısız        2 / 1281 (%0,2) — tek CCD: WJS
SMARTS               39/39 geçerli · 8/8 pozitif · 6/6 negatif · 8/8 hiyerarşi
```

## Önerilen dosyalar

**Yeni:** `pipeline/enrichment/audit_ligand_chemistry.py` ·
`pipeline/enrichment/build_ligand_chemistry.py` ·
`config/enrichment/chemistry_catalog.json` ·
`schemas/enrichment/ligand_chemistry.schema.json` ·
`tests/enrichment/test_chemistry_smarts.py` ·
`data/web/global/{ligand_chemistry,chemistry_catalog,ligand_chemistry_audit}.json`

**Değişecek:** `pipeline/phase5/build_payloads.py` (manifest kaydı) ·
`app/js/data/loader.js` · `app/js/views/views.js` · `app/js/core/i18n.js` ·
`app/css/atlas.css`

**Değişmeyecek:** temas verisi · farmakoloji sınıfları · panel payload'ları ·
mevcut 113 test

## Kesin MVP kapsamı

10 RDKit descriptor · 26 fonksiyonel grup · 13 halka sistemi · biyolojik tip filtresi ·
kimyasız instance sayacı · provenance görünürlüğü

## Kapsam dışı

assay · activity measurement · quantitative bias · reference ligand · transduction
coefficient · logD₇.₄ · scaffold/chemotype (Aşama 3) · substructure çizim · chemical space ·
contact enrichment istatistiği

## Beklenen bundle artışı

**≈ 292 KB** (255,8 + 6,3 + ~30) · mevcut 501 MB üzerine **%0,06** ·
landing ilk yükü **değişmiyor** (13.539 bayt)

## Açık kararlar

1. Chemotype listesi ve kaynağı (Aşama 3'ü başlatmadan)
2. Peptit ligandlar için alternatif descriptor MVP'ye girsin mi
3. `covalent_adduct` kimyasının temsili

## GO / NO-GO önerisi

**Aşama 0 ve 1 için GO.** Ölçümler yapıldı, araç (RDKit 2025.09.6) kurulu, girdi
(580 SMILES) yerel, desenler doğrulandı, boyut etkisi ihmal edilebilir, mimari mevcut
enrichment hattına oturuyor.

**Aşama 3 için NO-GO** — chemotype listesi bilimsel bir karar, henüz verilmedi.

**Aşama 2 (arayüz) şartlı GO** — Aşama 1'in kabul kriterleri geçtikten sonra.
