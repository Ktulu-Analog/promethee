---
name: Guide messagerie IMAP
description: >
  Protocole pour lire, rechercher, envoyer et gérer des emails via IMAP/SMTP
  avec les outils imap_*. Lister les dossiers, consulter les derniers messages,
  rechercher par critères, lire le contenu complet avec pièces jointes,
  envoyer et répondre à des emails.
tags: [imap, smtp, email, messagerie, courrier, pièces-jointes]
version: 1.0
---

# Guide messagerie IMAP

Guide pour lire et gérer les emails via les outils IMAP/SMTP disponibles dans Prométhée.

---

## 1. Workflows types

### Consulter les derniers messages
```
imap_list_mails(folder="INBOX", limit=20)
→ expéditeur, objet, date, taille pour chaque message

imap_read_mail(mail_id="...")
→ contenu complet : headers, corps, pièces jointes
```

### Rechercher un message précis
```
imap_search_mails(sender="direction@organisme.fr", subject="convocation")
→ liste des messages correspondants avec leurs IDs

imap_read_mail(mail_id="...")
→ lecture du message retenu
```

### Envoyer un message
```
imap_send_mail(to="destinataire@exemple.fr", subject="...", body="...")
```

### Répondre à un message
```
imap_reply_mail(mail_id="...", body="...")
→ conserve le fil de conversation (In-Reply-To)
```

---

## 2. `imap_list_folders` — lister les dossiers disponibles

```json
{}
```

Retourne les noms exacts des dossiers du serveur IMAP.
**Toujours appeler en premier** si on ne connaît pas les noms de dossiers exacts — ils varient selon le serveur (`Envoyés`, `Sent`, `Sent Messages`, etc.).

---

## 3. `imap_list_mails` — consulter les derniers messages

```json
{
  "folder": "INBOX",
  "limit": 20
}
```

Retourne les N messages les plus récents : expéditeur, destinataires, objet, date, taille, indicateurs (lu/non-lu, important).

**Dossiers courants :**

| Dossier | Variantes fréquentes |
|---|---|
| Boîte de réception | `INBOX` |
| Messages envoyés | `Sent`, `Envoyés`, `Sent Messages` |
| Brouillons | `Drafts`, `Brouillons` |
| Corbeille | `Trash`, `Corbeille`, `Deleted Messages` |
| Spam | `Junk`, `Spam` |

→ Utiliser `imap_list_folders` si le dossier n'est pas trouvé.

---

## 4. `imap_search_mails` — recherche multicritères

```json
{
  "folder": "INBOX",
  "sender": "rh@organisme.fr",
  "subject": "congé",
  "since": "2026-01-01",
  "unseen": true,
  "limit": 50
}
```

**Paramètres disponibles :**
- `sender` : filtrer par expéditeur
- `recipient` : filtrer par destinataire
- `subject` : filtrer par objet (recherche partielle)
- `body` : filtrer par contenu du corps
- `since` / `before` : plage de dates (format `YYYY-MM-DD`)
- `unseen` : `true` pour les non-lus uniquement
- `flagged` : `true` pour les messages importants (étoilés)

---

## 5. `imap_read_mail` — lire un message complet

```json
{
  "mail_id": "12345"
}
```

Retourne :
- **Headers** : expéditeur, destinataires, CC, objet, date, message-ID
- **Corps** : texte brut et/ou HTML
- **Pièces jointes** : nom, type MIME, taille, contenu en base64

**Note sur les pièces jointes :** les fichiers PDF, images et documents Office sont retournés en base64. Pour les traiter, utiliser `ocr_pdf` (PDF scannés), `data_file_tools` (Excel), ou `python_exec` pour tout traitement personnalisé.

---

## 6. `imap_send_mail` — envoyer un message

```json
{
  "to": "destinataire@exemple.fr",
  "subject": "Réponse à votre demande",
  "body": "Madame, Monsieur,\n\nSuite à votre demande...",
  "cc": "copie@exemple.fr",
  "html_body": "<p>Version HTML optionnelle</p>"
}
```

- `to` : adresse du destinataire (ou liste séparée par des virgules)
- `cc` / `bcc` : copie et copie cachée (optionnels)
- `body` : corps en texte brut
- `html_body` : corps HTML (optionnel, complète `body`)
- `attachments` : pièces jointes en base64 (optionnel)

L'expéditeur est défini par la configuration SMTP dans `.env`.

---

## 7. `imap_reply_mail` — répondre à un message

```json
{
  "mail_id": "12345",
  "body": "Bien reçu, nous donnerons suite...",
  "reply_all": false
}
```

Conserve automatiquement les headers `In-Reply-To` et `References` pour maintenir le fil de conversation dans les clients mail.

- `reply_all: true` → répond à tous les destinataires du message original

---

## 8. `imap_mark_mail` — marquer un message

```json
{
  "mail_id": "12345",
  "action": "read"
}
```

**Actions disponibles :**

| Action | Effet |
|---|---|
| `read` | Marquer comme lu |
| `unread` | Marquer comme non-lu |
| `flagged` | Marquer comme important (étoile) |
| `unflagged` | Retirer le marquage important |
| `deleted` | Marquer pour suppression (⚠️ exige un EXPUNGE côté serveur pour être définitif) |

---

## 9. `imap_move_mail` — déplacer un message

```json
{
  "mail_id": "12345",
  "destination": "Archives/2026"
}
```

Utiliser `imap_list_folders` au préalable pour connaître le nom exact du dossier de destination.

---

## 10. Bonnes pratiques

- **Toujours utiliser `imap_list_folders`** si les dossiers sont inconnus — les noms varient selon les serveurs.
- **Préférer `imap_search_mails`** plutôt que `imap_list_mails` + tri manuel pour retrouver un message précis.
- **Les pièces jointes volumineuses** (> 5 Mo) peuvent ralentir `imap_read_mail` — l'indiquer à l'utilisateur avant de lire.
- **Ne jamais composer une URL de désinscription ou de lien externe** à partir du contenu d'un email — risque de phishing.

---

## 11. Erreurs fréquentes

| Erreur | Correction |
|---|---|
| Dossier introuvable | Appeler `imap_list_folders` pour obtenir les noms exacts |
| Message non trouvé par ID | L'ID IMAP peut changer si la boîte est réorganisée — relancer `imap_search_mails` |
| Envoi échoué | Vérifier la configuration SMTP dans `.env` (host, port, user, password) |
| Corps vide à la lecture | Le message peut être HTML uniquement — vérifier le champ `html_body` dans le retour |
