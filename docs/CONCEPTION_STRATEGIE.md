# Conception d'une stratégie d'allocation dynamique de budget — document de synthèse

*Produit par un panel de cinq agents spécialisés (méthodes quantitatives, données, risque,
statistiques de validation, avocat du diable) travaillant indépendamment sur le même cahier des
charges, avec accès aux ~500 backtests réels de ce dépôt, puis confrontés en comité. Les conflits
entre spécialistes et leurs résolutions sont documentés — le résultat final est celui qui survit
aux cinq relectures, pas un consensus mou.*

---

## 1. Analyse du problème

**Formalisation.** C'est un problème de contrôle stochastique : à chaque instant t, l'état est
(réserve de cash R_t, jours avant recharge du budget, état de marché), l'action est la fraction
u_t ∈ [0,1] de R_t à déployer et sa destination parmi 2-3 ETF. Contraintes : pas de levier, pas de
vente (empiriquement −16 à −41 % de patrimoine OOS sur les 84 paires testées, plus fiscalité hors
PEA). Objectif : maximiser E[U(W_T)] (CRRA), c'est-à-dire la croissance ajustée du risque.

**L'asymétrie qui gouverne tout le design.** Sur cet univers et à ces horizons :

- **La moyenne conditionnelle est inapprenable.** SNR journalier ≈ 0,025 (μ ≈ 3 pb/j contre
  σ ≈ 115 pb/j) ; mensuel ≈ 0,13. Sur 25 ans on dispose de ~312 décisions mensuelles, mais avec le
  clustering de régimes l'échantillon effectif est de **15-25 blocs indépendants**. L'erreur-type
  d'un Sharpe estimé sur 25 ans est ~0,20 : deux politiques dont les vrais Sharpe diffèrent de
  moins de 0,4 sont indistinguables. Confirmer un edge de +1 %/an à 2σ contre 16 % de vol demande
  ~1 000 ans de données.
- **La variance est apprenable.** La vol réalisée est quasi observable, sa persistance donne des
  R² out-of-sample de 30-60 % (HAR-RV/GARCH) avec 3-5 paramètres. Mais — point crucial établi par
  l'audit des données — dans un système achat-seul sans levier, **l'espace d'action ne peut pas
  monétiser cette prévisibilité** : dé-risquer exige de vendre ou du levier, tous deux exclus.

**Le « budget comme ressource stratégique ».** L'intuition « garder des munitions pour de
meilleures opportunités » a une valeur d'option **négative** : sous prix ≈ martingale + drift
positif, attendre coûte μ·dt ≈ 2,8 pb/jour (~58 pb/mois) sans valeur d'option compensatrice — le
droit d'acheter moins cher est exactement payé par le drift auquel on renonce. Les frais
proportionnels sans minimum ne justifient aucun report. C'est démontrable en contrôle optimal et
cohérent avec nos données.

## 2. Comparaison critique des approches

| Approche | Besoin en données vs ~300 décisions (N_eff 15-25) | Ce qu'elle apprendrait ici | Verdict |
|---|---|---|---|
| **RL profond** (PPO/DQN) | 10⁵-10⁷ transitions ; on a UNE trajectoire non stationnaire | Redécouvrirait « déploie tout, achète le gagnant récent » après des millions de pas de simulateur — politique exprimable en 2 lignes ; le simulateur réintroduit un modèle de rendement, donc la moyenne inapprenable | **Rejeté** : 3-4 ordres de grandeur de données manquants ; politique optimale déjà connue en forme fermée |
| **RL tabulaire / DP appris** | Une table modeste 3×3×5×4 = 180 cellules → <2 visites/cellule | Des probabilités de transition dominées par le bruit d'échantillonnage | **Rejeté** pour l'apprentissage ; **accepté comme outil de dérivation** avec modèle postulé (Merton) |
| **Bandits contextuels** | Regret O(√(KT log T)) : ~30 % de l'échantillon brûlé à explorer des bras dont l'écart vrai (~0,05-0,1σ) est indétectable dans T | Des posteriors quasi uniformes | **Rejeté** : la réduction en bandit jette la structure connue (drift > 0) qui résout déjà le problème ; récompenses différées sur des décennies |
| **Contrôle optimal stochastique** | Zéro donnée pour la forme de la politique ; 2-3 constantes de calibration | w* = μ/(γσ²) ≈ 0,8-1,3 → **la contrainte sans-levier sature** → politique bang-bang : tout déployer immédiatement | **Accepté comme couche 0** — il explique nos propres résultats empiriques a priori |
| **Décision bayésienne + shrinkage** | Fonctionne à tout N — l'honnêteté suit l'échantillon | Le posterior du premium momentum, nourri de US (+), FR (~0), FR3 (<0) et SE(Sharpe) ≈ 0,2, **rétrécit le tilt vers ~0** | **Accepté comme calcul de décision** — et sa conclusion est de ne pas tilter |
| **ML supervisé (rendements)** | Gu-Kelly-Xiu : R² mensuel 0,4-1 % avec 30 000 actions × 60 ans ; ici 2-3 actifs corrélés | En IS : des motifs éblouissants ; OOS : rien qui passe la barre de 55 pb/ordre (notre FR3 : IS +26,5 % → OOS −0,7 %) | **Rejeté** sauf un facteur pré-enregistré appuyé par la littérature (momentum 3-12 m) — jamais un apprenant libre |
| **ML supervisé (variance)** (HAR-RV/GARCH) | 3-5 paramètres sur 6 500 barres : faisable et réplicable | Des prévisions de σ_t réelles… que l'espace d'action achat-seul **ne peut pas monétiser** (nos grilles : vol-target et dip-boost inertes OOS) | **Rejeté en production** ; modèle élégant sans action rentable attachée |
| **Ensembles adaptatifs** | Chaque poids appris = un paramètre de plus sur 15-25 blocs effectifs | Notre re-pondération IC walk-forward, testée : du bruit (fenêtres chevauchantes) | **Rejeté** |

**Pourquoi le contrôle optimal + décision bayésienne l'emporte** : c'est la seule combinaison dont
la consommation de données correspond au budget de données disponible. Le contrôle fournit la
*forme* de la politique sans rien estimer ; le bayésien fournit la *discipline* pour dimensionner
ce qui resterait à estimer — et conclut, sur nos propres données, qu'il n'y a rien à estimer de
manière fiable.

## 3. Choix de l'approche — et deux erreurs d'attribution corrigées

Le comité a d'abord dû trancher deux conflits majeurs, parce que l'avocat du diable a démonté,
chiffres du dépôt en main, deux conclusions antérieures de ce projet :

**Correction n° 1 — le « +19 % du déploiement immédiat » était une erreur d'attribution.** Le
harnais dépose le cash au 1er du mois alors que le benchmark DCA achète le 26, et le contrôle
« sans signal » détenait 50/50 SPY/QQQ contre un benchmark 100 % SPY. Décomposition exacte :
US OOS +19,0 % = **+19,2 % d'effet de composition (tilt Nasdaq) + (−0,2 %) de timing pur**. Le
timing calendaire vaut ~+0,05 %/an, pas +19 %. *La politique survit néanmoins sur la théorie
seule* (attendre coûte ~2,8 pb/jour) : on déploie à l'arrivée du cash, valorisé honnêtement à
~+0,05 %/an, pas comme source d'alpha.

**Correction n° 2 — le momentum de production est tué.** Trois arguments indépendants, aucun
réfuté : (i) *multiplicité* : meilleur Sharpe OOS de la grille 0,76-0,78 contre un seuil de Sharpe
déflaté ≈ 1,07 (sélection parmi ~106 variantes, ~1,3 échantillons effectifs — les trois « marchés »
de validation sont corrélés à 0,94-0,97) ; (ii) *le test du benchmark naïf* : la rotation momentum
**sous-performe le DCA-naïf-dans-QQQ qu'elle découvre implicitement de −5,8 à −13,3 % OOS sur les
trois marchés** — c'est une machine à convertir une décision de bêta en frais et en whipsaw ;
(iii) le propre cadre bayésien du spécialiste quant rétrécit le tilt à ~0. La décision d'exposition
growth devient donc **explicite et assumée comme choix de risque** (pondération fixe pré-enregistrée,
p. ex. 70/30 large/growth), pas déguisée en signal.

**L'approche retenue : l'« Accumulateur Structurel » — zéro paramètre ajusté en production.**
Chaque règle retenue se justifie structurellement (drift > 0, contrainte de Kelly saturée, frais
certains) ou comportementalement — jamais par une victoire de backtest. Edge honnête attendu vs
DCA du 26 : **+0,4 à +0,6 %/an, dont ~85 % vient des frais/TER/enveloppe et ~0 du timing — et tout
est certain.** C'est le résultat central : à cette échelle de données et d'univers, la
sophistication rentable n'est pas dans la règle de décision, elle est dans la structure de coûts
et dans l'infrastructure de validation.

## 4. Architecture complète

**Couche 0 — Structure (fait l'essentiel du travail).**
PEA maximisé avant tout autre compte (17,2 % vs 30 % PFU : plusieurs % de patrimoine final).
Courtier ≤ 0,2 %/ordre (cible ~0,1 %) : passer de 0,5 % à 0,15 % = **+0,35 % certain sur chaque
euro jamais investi**, plus que la valeur plausible de tous les signaux réunis. Univers gelé :
2-3 ETF UCITS indiciels bas-TER éligibles PEA (ligne large S&P/monde + ligne growth optionnelle),
classes EUR non couvertes (le hedge coûte ~1,5-2,3 %/an de carry pour économiser ~1 pt de vol),
émetteurs diversifiés si une ligne s'ajoute. Données : clôtures quotidiennes, rien d'autre.

**Couche 1 — Déploiement.** invest_t = **100 % du cash disponible**, le jour où il arrive
(déterminer le vrai jour d'arrivée — 26 ou paie — est le premier point d'action : c'est le seul
fait qui peut annuler la règle). Un ordre par ligne, pondérations de flux **fixes et
pré-enregistrées** (p. ex. 70/30). Pas de momentum, pas de rotation, pas de règle de creux, pas de
pacing, pas de réserve. Ordre programmé de secours au jour 28 si aucune action manuelle. Tout cash
opérationnellement inactif dort en ETF monétaire PEA (~ESTER).

**Couche 2 — Garde-fous (flux seulement, sans estimation).**
Cap de concentration : si la ligne growth > 60 % de la valeur du portefeuille, 100 % du flux du
mois va sur la ligne large jusqu'à repasser sous le cap (coût nul, impôt nul, jamais de vente ;
borne le pire scénario type 2000 de ~−81 % vers ~−65 %). Exécution : ordre limite au milieu de
fourchette ; si le spread > 25 pb, on saute la journée et on réessaie demain (un jour de délai
coûte ~3 pb ; un spread de crise en coûte 10-30×).

**Couche 3 — Gouvernance et surveillance (en production).**
Deux portefeuilles fantômes avec les flux réels du compte : N1 = DCA du 26 ; N2 = déploiement
immédiat aux mêmes pondérations. Garde de coût (déclencheur principal d'arrêt) : coût réalisé
tout-compris > 0,70 %/ordre ou dérive de frais 12 mois > modèle +0,3 pt → stop, corriger
courtier/exécution. Le déploiement immédiat n'est **jamais** tué sur la performance (il est
structurel) ; revue annuelle uniquement.

## 5. Données : audit famille par famille

| Famille | Contenu prédictif réel (horizon jours→mois) | Limites ici | Coût | Impact attendu | Verdict |
|---|---|---|---|---|---|
| Prix/clôtures quotidiennes | Momentum 3-12 m : le seul signal de moyenne robuste en littérature | Sur 2-3 ETF corrélés (ρ 0,91-0,93) : une seule vraie dispersion à exploiter ; échoue au test du benchmark naïf | 0 | Base du système | **Gardé** (seule famille) |
| Vol réalisée | La quantité la plus prévisible de la finance (R² 30-60 %) | **Non monétisable** achat-seul sans levier ; testée inerte OOS | 0 | ~0 ici | Rejeté en prod |
| Vol implicite (VIX/VSTOXX, terme) | Info de régime marginale au-delà de la RV | La règle candidate (« VIX>VIX3M → déploie la réserve ») est vidée par le design : réserve ≈ 0 et déploiement déjà immédiat | ~0 | ~0 | Rejeté ; piste recherche pré-enregistrée seulement |
| Intraday | ~0 de prévisibilité exploitable après 55 pb/ordre ; testé (cadences journalière/hebdo perdent) | Latence, complexité | Moyen | Négatif | Rejeté |
| Volume/liquidité | Sans objet à 1 k€/ordre sur des ETF à milliards d'ADV | — | 0 | 0 | Rejeté |
| Breadth | Redondant avec tendance/momentum sur cet univers | 2-3 actifs : pas de « largeur » à mesurer | Moyen | ~0 | Rejeté |
| Macro (taux, inflation, PMI) | Prédictif à 1-5 ans, avec délais de publication ; R² mensuel ~0,5-1 % (Goyal-Welch) non monétisable sans levier | Snooping massif, régime-dépendant | Moyen | ~0 | Rejeté |
| Sentiment / flux ETF / options | Alpha bref, capacitaire, bruyant | Sans objet à l'échelle retail mensuelle | Élevé | ~0 | Rejeté |
| On-chain | Pas de crypto dans l'univers | — | — | — | N/A |

**Le principe qui a tranché** : une donnée ne vaut ici que si elle peut bouger l'un des deux seuls
leviers — (a) retarder/accélérer ~1 000 €/mois (plafonné à quelques pb) ou (b) réorienter le flux
entre 2-3 ETF corrélés. La plupart des familles échouent non par absence d'information mais parce
que **l'espace d'action ne peut pas la monétiser**.

## 6. Algorithme de décision

Le jour d'arrivée du cash (pseudo-code intégral du système de production) :

```
cash        = solde espèces disponible
w_growth    = valeur_ligne_growth / valeur_portefeuille   # à la clôture de la veille
cible       = {large: 0.70, growth: 0.30}                 # pré-enregistré, choix de RISQUE
si w_growth > 0.60 :  cible = {large: 1.00, growth: 0}    # cap de concentration
pour chaque ligne avec cible > 0 :
    si spread_affiché > 25 pb : réessayer demain
    sinon : ordre limite au milieu, montant = cash × cible[ligne]
# jamais de vente ; pas d'autre décision ce mois-ci
```

**Sur les sorties probabilistes demandées** (P(bon point d'entrée), espérance, confiance, risque,
montant optimal, réserve) — le système les calcule et voici sa réponse honnête : le posterior du
rendement excédentaire conditionnel à toute variable d'entrée disponible est **plat au niveau de
précision atteignable** (SE ≈ 0,24 %/mois sur μ contre des effets candidats < 0,1 %/mois). La
décision d'espérance-utilité maximale **ne conditionne donc sur rien** : P(bon point d'entrée) =
P(prime de risque > 0 sur l'horizon) ≈ constante ; montant optimal = tout le cash (§7) ; réserve
optimale = 0 ; confiance = élevée sur la politique, faible sur toute prévision de rendement — et
c'est précisément pourquoi la politique ne dépend pas de prévisions. Produire un score d'entrée
« intelligent » à partir de ces données serait de la fausse précision, pas de la sophistication.

## 7. Gestion dynamique du budget

L'arithmétique de Kelly inverse la conclusion habituelle. μ mensuel ≈ 0,6-0,9 %, σ ≈ 4,5 %, cash
≈ 0,17 %/mois → **f\* = μ_excès/σ² ≈ 2,2-3,7** : Kelly plein voudrait 220-370 % d'exposition. La
contrainte sans-levier (f ≤ 1) sature donc en permanence : être investi à 100 % équivaut déjà à un
Kelly fractionnaire c ≈ 0,27-0,45 — profondément du côté conservateur. L'erreur d'estimation ne
change rien (le shrinkage bayésien déplace f\* de 2,22 à 2,21) ; P(vrai f\* < 1) ≈ 16 % et son coût
de croissance à f = 1 est du second ordre. **Conclusion : la réserve de cash n'a aucune
justification de sizing.** Le « budget ressource stratégique » a une valeur d'attente négative ;
sa gestion optimale est de ne pas exister. Le cash opérationnel (délais d'ordre, règlement) dort
en ETF monétaire ; le fonds d'urgence est un objet de finances personnelles hors système.

## 8. Gestion du risque

Dans un système achat-seul, on ne contrôle ni le drawdown du stock existant ni le marché ; on
contrôle **la direction des flux, la concentration, l'exécution et l'opérateur** :

- **Concentration** : cap growth ≤ 60 % (le seul « rééquilibrage » est par flux — gratuit et non
  imposable).
- **Exécution** : la fourchette des UCITS Euronext peut passer de 5 à 30-100 pb en crise — règle
  des 25 pb ci-dessus.
- **Structurel** : ETF synthétiques → préférer deux émetteurs ; classes non couvertes (l'USD offre
  une couverture de crise partielle gratuite).
- **Comportemental — le premier facteur de risque du système** : une seule vente panique coûte
  16-41 % du patrimoine, soit 20-40 ans de n'importe quel edge plausible. D'où : une décision par
  mois, une carte de règles qui tient sur un écran de téléphone, un ordre automatique de secours,
  et un **document de pré-engagement signé avant le premier euro** : « attends-toi à −15 % chaque
  année, −35 % chaque décennie, −55 % une fois ; les seules réponses permises sont continuer à
  acheter et appliquer le cap ; vendre n'est pas un levier. » Toute fonctionnalité qui augmente la
  probabilité d'abandon de plus de ~2 % a une espérance négative quel que soit son backtest.

**La carte de règles (le système entier)** : *« Achète le jour de paie. Tout. 70/30. Si growth >
60 %, n'achète que du large. Spread > 25 pb, attends demain. Ne vends jamais. »*

## 9. Méthodologie de validation

**Aveux préalables** (conditions de validité de tout ce qui précède) : notre OOS 2000-2026 est
**brûlé** — les métriques OOS des 325 runs ont été lues et ont façonné les conclusions ; toute
confirmation nouvelle exige du walk-forward post-2026-07 pré-enregistré ou des données jamais
touchées, lues une fois. Et les trois marchés de validation valent **~1,3 échantillons
indépendants** (corrélations 0,94-0,97), pas 3.

**Le pipeline de promotion** — prix d'entrée obligatoire pour tout candidat futur (réactivation du
momentum, VIX, univers élargi), le système de production n'ayant, lui, aucun paramètre à valider :

1. **Élagage & nulls gelés** : ≤ 24 candidats réellement distincts ; N1 = DCA du 26 ; N2 =
   déploiement immédiat aux mêmes pondérations (le benchmark correct — leçon de la correction n° 1).
2. **CPCV avec purge et embargo** : 8 groupes contigus (~39 mois), purge 252 j, embargo 21 j,
   démarrage à froid par segment, 28 combinaisons → 7 chemins de backtest recousus ; passe si
   l'excès médian vs N2 > 0 sur ≥ 5/7 chemins.
3. **Stabilité de voisinage** : ≥ 80 % des voisins de grille du même signe ; un argmax > 25 %
   au-dessus de son propre plateau est rejeté comme bruit ; survie du signe à frais 0,25-1,0 %.
4. **Lecture OOS unique ajustée de la multiplicité** : SPA de Hansen (bootstrap stationnaire,
   blocs ~6 mois, B = 10 000) ET Sharpe déflaté au-dessus du seuil ≈ 1,07 (E[max] sur N_eff ≈ 20
   essais corrélés).
5. **Monte-Carlo par bootstrap de blocs joint** (vecteur de rendements multi-actifs rééchantillonné
   ensemble, blocs ~42 j, B = 2 000, machine de flux complète rejouée) : soutenu ssi le 5ᵉ centile
   du ratio de richesse vs N2 > 1 à 10 ans.
6. **Tranches de régime** : gains ≥ −2 pt dans la décennie perdue 2000-2009 ; aucune tranche ne
   porte > 50 % de l'excès ; et **confirmation finale uniquement en walk-forward post-2026,
   +0,3 %/an de XIRR vs N2**, robuste à `--oos-shift` et aux frais 0,1-0,75 %.

En production, seule la **surveillance** tourne (étape 6 du protocole) : portefeuilles fantômes N1/N2
avec les flux réels, garde de coût, CUSUM à −5σ_m pour tout tilt éventuellement adopté (gelé, puis
réversion permanente à N2 si l'excès 36 mois < −2σ_m·√36). Le tableau de bord imprime l'énoncé de
puissance : *« confirmer +1 %/an ici demande des décennies — la surveillance détecte la casse, pas
les edges. »* Anti-look-ahead : convention signal-à-la-clôture-de-la-veille, et le test du triplement
de barre (tripler l'OHLC du jour ne doit changer aucun ordre) — il a attrapé un vrai bug dans ce
dépôt. Corrections de harnais requises avant toute nouvelle recherche : dépôt du cash le 26 (le
moteur dépose actuellement au 1er), rendement du cash, frais minimums de courtier, benchmark N2.

## 10. Améliorations futures

Classées par valeur ajustée de la certitude :

1. **Frais de courtage** (~+0,35 % certain de tout capital investi) — un formulaire, pas un backtest.
2. **TER et choix des lignes** (~0,15-0,25 %/an certain).
3. **Maximisation du PEA** (plusieurs % de patrimoine final vs CTO).
4. **Automatisation de l'achat** (supprime l'opérateur, premier facteur de risque).
5. **Corrections du harnais** (dépôt le 26, cash rémunéré, min fees, benchmark N2).
6. **Recherche — la seule piste à espérance positive** : élargir l'univers avec de la **vraie
   dispersion** (émergents, small caps, or), car la valeur de toute allocation dynamique croît avec
   la dispersion cross-sectionnelle — 2 ETF corrélés à 0,93 ne donnent presque rien à choisir. Via
   le pipeline complet du §9 exclusivement.
7. Momentum et VIX restent des candidats *pré-enregistrés* de cette piste — fermés par défaut.

**Le verdict final du comité, assumé comme un résultat et non comme un échec** : signaux conservés
en production — **aucun**. Sur cet univers, à cette échelle de données, après frais réels, le
système optimal qu'un fonds quantitatif construirait honnêtement est un accumulateur structurel à
zéro paramètre, entouré d'une infrastructure de validation assez dure pour empêcher quiconque —
y compris ses concepteurs — de se raconter des histoires.
