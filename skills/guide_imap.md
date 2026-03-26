---
name: Guide messagerie IMAP
description: >
  Protocole complet pour lire, rechercher, envoyer et gérer des emails via
  les outils imap_*. Couvre les règles de rédaction (HTML obligatoire,
  ton professionnel, signature Prométhée), les paramètres exacts de chaque
  outil, les workflows types et les bonnes pratiques.
tags: [imap, smtp, email, messagerie, courrier, pièces-jointes, rédaction, html, signature]
version: 2.0
---

# Guide messagerie IMAP

Guide opérationnel pour exploiter les outils IMAP/SMTP de Prométhée :
lecture, recherche, envoi, réponse, classement et gestion des messages.

---

## 1. Règles de rédaction — à respecter impérativement

### 1.1 Format : HTML obligatoire, Markdown interdit

Tout mail rédigé et envoyé par Prométhée **doit être au format HTML**.
Le Markdown n'est pas un format email standard : les astérisques, dièses et
tirets apparaissent tels quels dans les clients mail des destinataires.

**Toujours renseigner `corps_html`** avec le contenu HTML mis en forme,
et fournir également `corps` avec une version texte brut de repli
(pour les clients mail qui n'affichent pas le HTML).

Structure HTML minimale d'un mail :

```html
<html>
<body style="font-family: Arial, sans-serif; font-size: 14px; color: #222222; line-height: 1.6;">

  <p>Madame, Monsieur,</p>

  <p>Corps du message.</p>

  <p>Cordialement,</p>

  <!-- Signature obligatoire — voir section 1.3 -->

</body>
</html>
```

**Éléments HTML autorisés et recommandés :**

| Besoin | Balise à utiliser |
|---|---|
| Paragraphe | `<p>` |
| Titre de section | `<h3>` ou `<h4>` (ne pas utiliser `<h1>`/`<h2>` dans un mail) |
| Liste à puces | `<ul><li>…</li></ul>` |
| Liste numérotée | `<ol><li>…</li></ol>` |
| Texte en gras | `<strong>` |
| Texte en italique | `<em>` |
| Lien hypertexte | `<a href="url">texte</a>` |
| Tableau | `<table>` avec `border="0"` et `cellpadding="6"` |
| Séparateur | `<hr style="border: none; border-top: 1px solid #dddddd;">` |

**Ne jamais utiliser :** `#`, `**`, `*`, `---`, `>` (syntaxe Markdown),
ni de CSS complexe ou de JavaScript.

### 1.2 Ton et style professionnels

- **Formule d'appel** : `Madame, Monsieur,` (générique) ou `Madame,` / `Monsieur,`
  si le genre est connu. Pour une réponse à une personne identifiée :
  `Madame [Nom],` ou `Monsieur [Nom],`.
- **Vouvoiement** systématique, même si le destinataire tutoie.
- **Formule de politesse finale** avant la signature :
  - Neutre : `Cordialement,`
  - Respectueuse (hiérarchie, institutionnel) :
    `Veuillez agréer, Madame, Monsieur, l'expression de mes salutations distinguées.`
  - Collégiale (collègue) : `Bien cordialement,`
- **Pas d'écriture inclusive** (pas de `·`, `/`, `(e)`).
- **Pas d'émoticônes** ni d'abréviations familières.
- **Objet** : court, informatif, sans ponctuation finale.
  Exemples : `Demande de rendez-vous — 15 janvier 2026`,
  `Transmission du rapport trimestriel`, `Réponse à votre courrier du 3 mars`.

### 1.3 Signature obligatoire

Tout mail envoyé ou rédigé par Prométhée **doit inclure la signature suivante**
à la fin du corps HTML, avant la balise `</body>` :

```html
<hr style="border: none; border-top: 1px solid #dddddd; margin: 24px 0 12px;">
<p style="font-size: 12px; color: #888888; margin: 0;">
  <em>Ce message a été rédigé et envoyé par <strong>Prométhée</strong>,
  assistant IA — à la demande de l'utilisateur.</em>
</p>
```

Version texte brut de repli à inclure dans le champ `corps` :

```
--
Ce message a été rédigé et envoyé par Prométhée, assistant IA — à la demande de l'utilisateur.
```

### 1.4 Objet d'une réponse

Ne pas modifier l'objet lors d'un `imap_reply_mail` : l'outil ajoute
automatiquement le préfixe `Re:` si absent. Ne fournir le paramètre `objet`
que pour les nouveaux messages ou les transferts.

---

## 2. Référence des outils — paramètres exacts

### `imap_list_folders`

Liste les dossiers disponibles sur le serveur IMAP.
**Appeler en premier** si les noms de dossiers sont inconnus.

```json
{
  "profil": "pro"
}
```

Tous les paramètres sont optionnels. Sans `profil`, utilise le compte par défaut.

---

### `imap_list_mails`

Liste les N derniers messages d'un dossier.

```json
{
  "dossier": "INBOX",
  "n": 20,
  "non_lus_seulement": false,
  "profil": null
}
```

| Paramètre | Type | Défaut | Description |
|---|---|---|---|
| `dossier` | string | `"INBOX"` | Nom exact du dossier IMAP |
| `n` | integer | `20` | Nombre de messages (max 100) |
| `non_lus_seulement` | boolean | `false` | Filtrer sur les non-lus |
| `profil` | string | null | Préfixe du compte dans `.env` |

Retourne : `uid`, `from`, `to`, `subject`, `date`, `lu`, `important`.

---

### `imap_search_mails`

Recherche multicritères dans un dossier. Tous les critères sont cumulatifs (ET logique).

```json
{
  "dossier": "INBOX",
  "expediteur": "drh@organisme.fr",
  "destinataire": null,
  "objet": "convocation",
  "corps": null,
  "depuis": "2026-01-01",
  "jusqu_au": "2026-03-31",
  "non_lus_seulement": false,
  "n": 20,
  "profil": null
}
```

| Paramètre | Type | Description |
|---|---|---|
| `expediteur` | string | Recherche partielle sur FROM |
| `destinataire` | string | Recherche partielle sur TO |
| `objet` | string | Recherche partielle sur SUBJECT |
| `corps` | string | Recherche dans le corps (lent sur grandes boîtes) |
| `depuis` | string | Date de début `YYYY-MM-DD` |
| `jusqu_au` | string | Date de fin `YYYY-MM-DD` |
| `non_lus_seulement` | boolean | Filtrer sur UNSEEN |
| `n` | integer | Max résultats (max 50) |

---

### `imap_read_mail`

Lit le contenu complet d'un message. **Marque le message comme lu automatiquement.**

```json
{
  "uid": "4271",
  "dossier": "INBOX",
  "inclure_html": false,
  "inclure_pj": true,
  "profil": null
}
```

Retourne : `message_id`, `from`, `to`, `cc`, `subject`, `date`, `body`,
`in_reply_to`, `references`, `attachments` (liste avec `filename`,
`content_type`, `size_bytes`, `data_base64` pour PDF/images/Office).

---

### `imap_send_mail`

Envoie un nouveau message. L'expéditeur est défini par `IMAP_FROM` (ou `IMAP_USER`) dans `.env`.

```json
{
  "destinataires": ["destinataire@exemple.fr"],
  "objet": "Transmission du rapport — mars 2026",
  "corps": "Madame, Monsieur,\n\nVeuillez trouver ci-joint...\n\n--\nCe message a été rédigé et envoyé par Prométhée.",
  "corps_html": "<html><body>...</body></html>",
  "cc": ["copie@exemple.fr"],
  "cci": ["archivage@exemple.fr"],
  "pieces_jointes": [
    {"chemin": "/home/pierre/Exports/rapport.pdf"},
    {"data_base64": "...", "nom_fichier": "annexe.xlsx", "type_mime": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}
  ],
  "profil": null
}
```

| Paramètre | Requis | Description |
|---|---|---|
| `destinataires` | ✓ | Liste d'adresses TO |
| `objet` | ✓ | Objet du mail |
| `corps` | ✓ | Corps texte brut (repli) |
| `corps_html` | — | Corps HTML (obligatoire si mise en forme) |
| `cc` | — | Copie |
| `cci` | — | Copie cachée |
| `pieces_jointes` | — | Liste de PJ (voir ci-dessous) |
| `profil` | — | Compte à utiliser |

**Format des pièces jointes (`pieces_jointes`) :**

Chaque élément est un objet avec **soit** `chemin` (chemin absolu du fichier sur disque),
**soit** `data_base64` + `nom_fichier` + `type_mime` (données base64) :

```json
// Depuis le disque (recommandé — type MIME détecté automatiquement)
{"chemin": "/home/pierre/Exports/Prométhée/rapport.pdf"}

// Depuis des données base64 (ex : PJ reçue et retransmise)
{"data_base64": "JVBERi0x...", "nom_fichier": "rapport.pdf", "type_mime": "application/pdf"}
```

> **Note MIME :** la présence de PJ force automatiquement un conteneur `multipart/mixed`.
> Si `corps_html` est également fourni, la structure sera `mixed > alternative (plain + html) + PJ`.
> Le type MIME est détecté automatiquement depuis l'extension si non fourni.

---

### `imap_reply_mail`

Répond à un message existant. Conserve `In-Reply-To` et `References`.
**Supporte désormais le HTML et les pièces jointes.**

```json
{
  "uid": "4271",
  "corps": "Madame,\n\nBien reçu...\n\n--\nCe message a été rédigé et envoyé par Prométhée.",
  "corps_html": "<html><body>...</body></html>",
  "dossier": "INBOX",
  "repondre_a_tous": false,
  "pieces_jointes": [
    {"chemin": "/home/pierre/Exports/reponse.pdf"}
  ],
  "profil": null
}
```

| Paramètre | Requis | Description |
|---|---|---|
| `uid` | ✓ | UID du mail original |
| `corps` | ✓ | Corps texte brut (repli) |
| `corps_html` | — | Corps HTML avec signature et citation |
| `dossier` | — | Dossier source (défaut : INBOX) |
| `repondre_a_tous` | — | Reply-All (défaut : false) |
| `pieces_jointes` | — | Même format que `imap_send_mail` |
| `profil` | — | Compte à utiliser |

> **Fil de conversation :** `imap_reply_mail` positionne toujours `In-Reply-To` et `References`
> correctement, y compris quand `corps_html` est fourni — contrairement à l'ancienne
> recommandation qui suggérait d'utiliser `imap_send_mail` pour contourner cette limitation.

---

### `imap_mark_mail`

Modifie les flags d'un message.

```json
{
  "uid": "4271",
  "action": "lu",
  "dossier": "INBOX",
  "profil": null
}
```

| Action | Effet serveur |
|---|---|
| `lu` | Ajoute `\Seen` |
| `non_lu` | Retire `\Seen` |
| `important` | Ajoute `\Flagged` (étoile) |
| `non_important` | Retire `\Flagged` |
| `supprime` | Ajoute `\Deleted` + EXPUNGE immédiat |

---

### `imap_move_mail`

Déplace un message vers un autre dossier.

```json
{
  "uid": "4271",
  "dossier_destination": "Archives/2026",
  "dossier_source": "INBOX",
  "profil": null
}
```

Utilise MOVE (RFC 6851) si le serveur le supporte, sinon COPY + DELETE.
Appeler `imap_list_folders` pour connaître le nom exact du dossier de destination.

---

## 3. Workflows types

### Consulter les derniers messages non lus

```
1. imap_list_mails(dossier="INBOX", n=20, non_lus_seulement=true)
   → liste uid, expéditeur, objet, date

2. imap_read_mail(uid="...", dossier="INBOX")
   → contenu complet, marque automatiquement comme lu
```

### Rechercher un message précis

```
1. imap_search_mails(expediteur="rh@organisme.fr", objet="congé", depuis="2026-01-01")
   → liste des messages correspondants avec leurs uid

2. imap_read_mail(uid="...")
   → lecture du message retenu
```

### Rédiger et envoyer un nouveau mail (avec ou sans PJ)

```
1. Rédiger le corps HTML avec signature Prométhée (section 1.3)
2. Préparer le corps texte brut de repli avec signature texte
3. imap_send_mail(
     destinataires=["..."],
     objet="...",
     corps="... [texte brut]",
     corps_html="<html>...</html>",
     pieces_jointes=[
       {"chemin": "/chemin/absolu/vers/fichier.pdf"},
       {"data_base64": "...", "nom_fichier": "annexe.xlsx", "type_mime": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}
     ]
   )
```

**Sources acceptées pour les pièces jointes :**
- Fichier généré sur disque → `{"chemin": "/home/pierre/Exports/rapport.pdf"}` (type MIME auto-détecté)
- Données base64 (ex : PJ reçue et retransmise) → `{"data_base64": "...", "nom_fichier": "doc.pdf", "type_mime": "application/pdf"}`

### Répondre à un message avec mise en forme HTML (et PJ optionnelle)

```
1. imap_read_mail(uid="...", inclure_html=false)
   → récupérer from, subject, date, body pour construire la citation

2. Construire le corps HTML de réponse avec :
   - La réponse rédigée
   - La signature Prométhée (section 1.3)
   - La citation du message original :
     <blockquote style="border-left: 3px solid #cccccc; padding-left: 12px; color: #666666;">
       <p><em>Le [date], [expéditeur] a écrit :</em></p>
       [corps original]
     </blockquote>

3. imap_reply_mail(
     uid="...",
     corps="... [texte brut de repli]",
     corps_html="<html>...</html>",
     pieces_jointes=[{"chemin": "/chemin/vers/fichier.pdf"}]  ← optionnel
   )
   → conserve automatiquement In-Reply-To et References
```

> Les headers de fil de conversation sont conservés même avec `corps_html` et des pièces jointes.

### Traitement d'une pièce jointe reçue

```
1. imap_read_mail(uid="...", inclure_pj=true)
   → attachments[].data_base64 pour PDF/images/Office

2. Selon le type :
   - PDF texte  → extraire le texte avec python_exec + PyMuPDF
   - PDF scanné → ocr_tools
   - Excel      → data_file_tools (lire depuis base64)
   - Word/PPT   → python_exec + python-docx / python-pptx
   - Image      → ocr_tools ou analyse directe
```

### Classer et archiver

```
1. imap_list_folders()
   → identifier le dossier d'archivage (ex: "Archives/2026")

2. imap_move_mail(uid="...", dossier_destination="Archives/2026")

3. Optionnel : imap_mark_mail(uid="...", action="lu")
```

---

## 4. Gestion multi-comptes (profils)

L'outil supporte plusieurs comptes via des profils définis dans `.env`.
Chaque profil correspond à un préfixe de variables d'environnement.

**Exemple — profil `pro` :**
```
IMAP_PRO_HOST=imap.monorganisme.fr
IMAP_PRO_PORT=993
IMAP_PRO_USER=pierre.dupont@monorganisme.fr
IMAP_PRO_PASSWORD=motdepasse
IMAP_PRO_SSL=ON
IMAP_PRO_FROM=pierre.dupont@monorganisme.fr
IMAP_PRO_DISPLAY_NAME=Pierre Dupont
SMTP_PRO_HOST=smtp.monorganisme.fr
SMTP_PRO_PORT=465
SMTP_PRO_USER=pierre.dupont@monorganisme.fr
SMTP_PRO_PASSWORD=motdepasse
```

Utilisation : `profil="pro"` dans tous les appels d'outils.
Sans `profil`, le compte par défaut (`IMAP_HOST`, `IMAP_USER`…) est utilisé.

**Authentification OAuth2 :** si `IMAP_[PROFIL_]OAUTH2_TOKEN` est défini,
il est utilisé en priorité sur le mot de passe (mécanisme XOAUTH2).

---

## 5. Dossiers IMAP courants

Les noms varient selon les serveurs et les clients mail.
Toujours vérifier avec `imap_list_folders` avant le premier usage.

| Usage | Noms fréquents |
|---|---|
| Boîte de réception | `INBOX` (universel) |
| Messages envoyés | `Sent`, `Envoyés`, `Sent Messages`, `INBOX.Sent` |
| Brouillons | `Drafts`, `Brouillons`, `INBOX.Drafts` |
| Corbeille | `Trash`, `Corbeille`, `Deleted Messages`, `INBOX.Trash` |
| Spam / Indésirables | `Junk`, `Spam`, `INBOX.Junk` |
| Archives | `Archive`, `Archives`, `All Mail` (Gmail) |

---

## 6. Comportements importants à connaître

- **`imap_read_mail` marque le message comme lu** automatiquement.
  Pour lire sans marquer, il n'y a pas de paramètre dédié — utiliser
  `imap_mark_mail(action="non_lu")` immédiatement après si nécessaire.

- **`imap_mark_mail(action="supprime")` est irréversible** : le message
  est supprimé définitivement (EXPUNGE effectué immédiatement).
  Préférer `imap_move_mail` vers la Corbeille pour une suppression récupérable.

- **Les UID IMAP ne sont pas permanents** sur tous les serveurs : ils peuvent
  changer si la boîte est réorganisée (compactage). Ne pas stocker les UID
  sur le long terme — toujours relancer une recherche si un UID est incertain.

- **Corps vide à la lecture** : certains messages sont HTML uniquement
  (le champ `body` est vide). Relire avec `inclure_html=true` pour obtenir
  le contenu HTML, puis en extraire le texte si besoin.

- **Pièces jointes volumineuses** : `imap_read_mail` avec `inclure_pj=true`
  peut être lent pour les messages avec des PJ > 5 Mo. Prévenir l'utilisateur
  avant de lancer la lecture. Si seules les métadonnées sont nécessaires,
  utiliser `inclure_pj=false`.

- **`imap_reply_mail` envoie en texte brut uniquement**. Pour une réponse
  HTML, construire la réponse manuellement avec `imap_send_mail` (voir section 3).

---

## 7. Erreurs fréquentes et corrections

| Erreur retournée | Cause probable | Correction |
|---|---|---|
| `Dossier '...' introuvable` | Nom de dossier incorrect | Appeler `imap_list_folders` pour obtenir les noms exacts |
| `AUTHENTICATIONFAILED` | Mauvais identifiants | Vérifier `IMAP_USER` / `IMAP_PASSWORD` dans `.env` |
| `Configuration incomplète` | Variables `.env` manquantes | Vérifier `IMAP_HOST`, `IMAP_USER`, `IMAP_PASSWORD` |
| `Mail UID ... introuvable` | UID expiré ou mauvais dossier | Relancer `imap_search_mails` pour retrouver l'UID |
| `Erreur envoi : SMTP...` | Config SMTP manquante ou incorrecte | Vérifier `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD` |
| `Corps vide` | Message HTML uniquement | Relire avec `inclure_html=true` |
| `Authentification SMTP échouée` | Mot de passe SMTP incorrect | Vérifier `SMTP_PASSWORD` (peut différer de `IMAP_PASSWORD`) |
