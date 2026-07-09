# appli_quiz . XTra Game 2026

Quiz live en salle. Le public vote depuis son telephone via QR code, le
classement inter-equipe s'affiche a l'ecran. L'application ne rejoue pas le
contenu des questions : les enonces et les figures vivent dans le PowerPoint,
l'animateur mene les deux en cadence.

## Les trois vues

- `/play` telephones. Jonction (pseudo + equipe), boutons de vote, resultat
  personnel, classement. Le QR pointe ici.
- `/present` ecran projete. Texte seul. En LOBBY : QR geant et compteur par
  equipe. En question ouverte : compteur de votes en direct. Apres fermeture :
  distribution des votes, bonne reponse, % corrects par equipe, classement.
  A la fin : classement final et tableau questions x equipes.
- `/host?key=HOST_KEY` vue de controle. Trois boutons : ouvrir la question
  suivante, fermer le vote et reveler, terminer.

## Choix de conception

- Score d'equipe = MOYENNE des totaux des membres, pas la somme. Impose par
  des tailles d'equipe heterogenes.
- Score individuel : 1000 points reponse juste instantanee, decroissance
  lineaire jusqu'a 500 au buzzer, 0 si faux. Le temps est mesure COTE SERVEUR.
- Le vote monte en POST HTTP, le WebSocket ne sert que de sonnette
  descendante : un gel de socket ne bloque jamais un vote.
- Revoter renvoie 200 already : un retry apres un gel reseau passe pour un
  succes. Un vote par personne par question, verrouille serveur.
- La bonne reponse n'est jamais presente dans l'API tant que la question est
  ouverte.
- Cookie strictement necessaire, signe HMAC, 12 h, httponly. Raison affichee
  explicitement avant jonction : retrouver la session apres deconnexion.
- UN SEUL worker uvicorn, obligatoire. L'etat vit en memoire du process.
  Plusieurs workers fragmenteraient l'etat et casseraient tout.

## Configuration

`quiz_config.json` : equipes et questions. `labels` = texte des boutons,
`correct_option` = index 0-base, `time_limit_s` = fenetre de vote.
ATTENTION : verifier `correct_option` des questions marquees `_todo`
(q0, q1, q2) avant le jour J. q3 (B) et q4 (NON) sont alignees sur le deck.

## Deploiement Render

1. Pousser sur GitHub. Le Blueprint `render.yaml` configure tout : service
   web Python gratuit, SECRET_KEY et HOST_KEY generees par Render.
2. Sur render.com : New > Blueprint > selectionner le repo > Apply.
   Le blueprint remplace l'ancien service lts-ws-probe si demande : accepter.
3. Lire HOST_KEY dans le dashboard : service > Environment > HOST_KEY.
4. URLs :
   - salle : `https://<service>.onrender.com/present`
   - controle : `https://<service>.onrender.com/host?key=<HOST_KEY>`
   - le QR affiche sur /present pointe vers /play automatiquement.

## Test local

    pip install -r requirements.txt pytest httpx
    python -m pytest -q            # 54 tests
    uvicorn main:app --workers 1   # http://127.0.0.1:8000/present

Sans variables d'environnement, HOST_KEY est generee et affichee au
demarrage dans le terminal.

## Runbook jour J

1. H-15 min : ouvrir /present sur le PC de projection. Ca reveille le
   service Render (le plan gratuit s'endort apres 15 min sans trafic,
   reveil environ 1 min). Les heartbeats WebSocket maintiennent ensuite
   le service eveille.
2. Ouvrir /host?key=... sur le telephone ou un 2e onglet de l'animateur.
3. La salle scanne le QR, choisit equipe et pseudo. Le compteur par equipe
   monte sur /present.
4. Slide question N du PowerPoint > bouton Ouvrir. Les telephones affichent
   les boutons. Le compteur de votes monte en direct.
5. Bouton Fermer > les telephones et l'ecran revelent. Passer a la slide
   revelation du PowerPoint.
6. Repeter. Apres la derniere question : bouton Terminer > classement final.
7. Export des statistiques : /api/export?key=<HOST_KEY> (JSON complet).

## Limites connues, assumees

- Etat en memoire : un crash ou un redeploy pendant le quiz remet a zero,
  les participants re-scannent. Risque accepte pour 5 questions / 20 min.
  Le port QuizRepository existe dans le domaine si une persistance devient
  necessaire un jour.
- Pas de limite de participants codee. Un process uvicorn tient tres
  largement une salle. La montee multi-noeuds (Redis) est hors perimetre.
- Une personne peut se recreer une identite en effacant ses cookies.
  Evenement interne convivial, pas de lutte anti-triche au-dela du
  verrouillage serveur un vote par identite par question.
- Render gratuit : premiere requete apres 15 min d'inactivite = reveil
  d'environ 1 min. Couvert par le point 1 du runbook.

## Architecture

    quizlive/domain/        regles metier pures, zero framework, zero I/O
      model.py              agregat Quiz, machine a etats, stats, classement
      scoring.py            politique de score (port + implementation)
      ports.py              Clock, EventPublisher, QuizRepository (Protocol)
    quizlive/application/   orchestration domaine <-> hub, DTOs d'etat
    quizlive/infra/         SystemClock, chargeur de config, hub WebSocket
    quizlive/web/           FastAPI, pages HTML inline, cookies, cle host
    main.py                 composition root
    tests/                  54 tests (machine a etats, votes, score,
                            classement, stats, accesseurs, couche web)

La machine a etats du serveur est la seule autorite :
LOBBY > OPEN(n) > CLOSED(n) > OPEN(n+1) ... > FINISHED.
Les telephones sont des ecrans passifs qui refetchent leur etat.
