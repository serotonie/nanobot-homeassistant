# Nanobot Conversation

Intégration de conversation Home Assistant pour l'API native `nanobot serve`.
Aucune modification du cœur de Home Assistant ou Nanobot.

## Installation

Dans HACS, ajouter `https://github.com/serotonie/nanobot-homeassistant`
comme dépôt personnalisé de catégorie **Intégration**, puis installer et
redémarrer Home Assistant. Installation manuelle : copier
`custom_components/nanobot_conversation` dans le répertoire `custom_components`
de la configuration Home Assistant.

Ajouter **Nanobot Conversation** dans Appareils et services. Renseigner le nom,
l'URL de base accessible depuis le conteneur Home Assistant
(par exemple `http://nanobot.example:8901`), la clé API et le délai maximal.
L'API doit être activée et protégée par un jeton bearer.

Dans le pipeline Assist, choisir cet agent et désactiver **Préférer traiter les
commandes localement** : l'intégration interroge elle-même l'agent natif avant
Nanobot. Aucun préfixe n'est requis.

## Routage et confidentialité

- Les réponses locales, y compris négatives, sont conservées.
- Seuls `no_intent_match` et `no_valid_targets` déclenchent Nanobot.
- Les erreurs d'exécution natives ne déclenchent ni repli ni nouvelle tentative.
- Nanobot reçoit exactement un message utilisateur et un identifiant de session.
  Son modèle, ses outils et sa mémoire restent configurés dans Nanobot.
- Les historiques sont séparés par intégration, utilisateur authentifié,
  appareil, satellite et conversation. Un satellite partagé ne permet pas
  d'identifier les membres de la famille : utiliser un agent familial sans
  mémoire privée.
- L'accès domotique de Nanobot doit être limité dans son serveur MCP aux
  appareils exposés dans Assist. Cette intégration ne modifie pas les
  permissions de l'agent distant.
- Les échecs réseau et d'authentification sont affichés comme erreurs et
  journalisés sans clé API. Les commandes ne sont jamais relancées
  automatiquement.

Compatibilité vérifiée avec Home Assistant **2026.10.4**. La voix nécessite
également un moteur STT/TTS configuré dans le pipeline.

## Développement

Structure et workflows inspirés du dépôt OVMS Trips Recorder : validations
HACS et Hassfest, tests, lint et publication séparés. Aucun frontend requis.

```sh
docker run --rm --network none --tmpfs /tmp \
  -v "$PWD:/repo:ro" --entrypoint python \
  ghcr.io/home-assistant/home-assistant:2026.10.4 \
  -m unittest discover -s /repo/tests -v
```

Le devcontainer utilise `docker-compose.dev.yml`. L'instance de développement
est accessible sur le port 18123 ; ses données locales ne sont pas suivies par
Git. La version du manifeste doit être mise à jour avant d'exécuter le workflow
Release, qui teste puis publie une archive et un tag correspondant.
