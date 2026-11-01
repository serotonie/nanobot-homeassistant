# Nanobot Conversation

Intégration de conversation Home Assistant pour l'API native `nanobot serve`
du [fork Nanobot de serotonie](https://github.com/serotonie/nanobot).
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
Git.

Pour publier, ouvrir **Actions → Release → Run workflow**, choisir la branche
**main**, saisir la version **X.Y.Z** sans préfixe `v` (par exemple **0.1.0**
pour la première release) et cocher **prerelease** si nécessaire.
Le workflow met à jour le manifeste, exécute les tests, commit la version si
elle change, puis publie le tag et l'archive sur ce même commit. Un tag existant
est refusé. Les règles de protection de `main` doivent autoriser ce commit par
GitHub Actions si une nouvelle version est demandée.

## Références et remerciements

Cette intégration s'appuie sur **Nanobot** pour le raisonnement, la mémoire de
conversation et l'exécution des outils. Merci aux auteurs et contributeurs de
[HKUDS/nanobot](https://github.com/HKUDS/nanobot), le projet d'origine, ainsi
qu'aux contributeurs du [fork utilisé ici](https://github.com/serotonie/nanobot).

- [API agent Nanobot](https://github.com/serotonie/nanobot/blob/main/docs/agent-api.md) :
  interface HTTP utilisée par cette intégration.
- [Documentation Nanobot](https://github.com/serotonie/nanobot/blob/main/docs/README.md) :
  installation, configuration des modèles, mémoire et outils MCP.
- [Home Assistant](https://www.home-assistant.io/) et
  [HACS](https://www.hacs.xyz/) : conversation Assist et distribution de
  l'intégration.
- [OVMS Trips Recorder](https://github.com/serotonie/ovms-home-assistant-trips-recorder) :
  référence pour la structure du dépôt et les workflows.

Ce dépôt est une intégration communautaire indépendante ; il ne fait pas partie
de Home Assistant Core ni du projet Nanobot d'origine.

## Licence

Distribué sous licence [MIT](LICENSE).
