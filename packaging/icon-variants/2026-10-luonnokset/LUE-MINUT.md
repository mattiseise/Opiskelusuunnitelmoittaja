# Kuvakeluonnokset D–G (lokakuu 2026)

Uusi kuvake Opintosuunnitelman muokkaajalle. Nykyinen kuvake (A, `packaging/icon.png`)
on ennallaan. Mitään ei ole vielä otettu käyttöön.

Kuvat tehdään uudelleen repon juuresta:

    .venv/bin/python -I packaging/icon-variants/2026-10-luonnokset/tee_kuvakkeet.py

## Konseptit

| | Nimi | Idea |
|---|---|---|
| **D** | Raahattava rivi | Taulukon kolme riviä kahdessa sarakkeessa (numero ja sisältö). Keskimmäinen rivi on kultainen ja irrotettu yhden ruudun verran sivuun, eli sitä ollaan siirtämässä. |
| **E** | Rivi lomakkeelle | Lomakearkki taitetulla kulmalla. Kaksi kenttää on jo täytetty, ja kultainen rivi on liukumassa arkin reunan yli lomakkeelle. |
| **F** | Aikajana | Opintojen osat porrastettuina palkkeina (Gantt) jaksosarakkeiden päällä. Kuvaa suunnitelmaa ajassa, ei suoraan sovelluksen toimintoa. |
| **G** | Rivi eteenpäin | Vaalea pergamenttipohja. Taulukon rivien välissä keskimmäinen rivi jatkuu kultaisena nuolena: rivi lähtee eteenpäin lomakkeelle. |

Kaikissa konsepteissa on sama logiikka: **taulukon rivit ovat kuvan aihe, ja kulta merkitsee
sitä riviä, jolle sovellus tekee jotain** (siirtää, vie lomakkeelle tai merkitsee valmiiksi).

## Suunnitteluperiaatteet

- Runko on Applen ruudukon mukainen: 824 px:n pyöristetty neliö 1024 px:n pohjalla,
  kulmasäde 185 px ja läpinäkyvä reunus.
- Sisältö on piirretty **16 × 16 -ruudukkoon**: 1 yksikkö = 64 px = 1 px 16 px:n
  kuvakkeessa. Reunat osuvat kokonaisiin yksiköihin, joten palkit pysyvät terävinä myös
  16 ja 32 px:n koossa.
- Ohuin sisältömuoto on 1 yksikkö (1/16 kuvakkeesta). G:n reunarengas on 0,5 yksikköä
  (tasan 1/32), ja se rajaa vaalean rungon vaaleaa taustaa vasten.
- Vain BC Helsinki -värit: pergamentti, pergamentti-2, burgundi, syvä burgundi ja kulta.
  Ei tekstiä, varjoja, liukuvärejä eikä pyöristettyjä sisämuotoja.
- D:n kaksi saraketta ovat tarkoituksellisia: kolme pelkkää palkkia näyttäisi
  ≡-valikkokuvakkeelta.

## Tiedostot

- `D-raahattava-rivi.png`, `E-rivi-lomakkeelle.png`, `F-aikajana.png`, `G-rivi-eteenpain.png`:
  1024 px, läpinäkyvä tausta rungon ulkopuolella.
- `vertailu.png`: D–G ja nykyinen A koossa 256, 64, 32 ja 16 px vaalealla (#ECECEC) ja
  tummalla (#1E1E1E) taustalla. Kuvat on pienennetty 1024 px:n lähteestä Lanczosilla
  samoin kuin Pillow tekee .ico-tiedostoon.
- `pikselitarkistus.png`: 16, 32 ja 48 px pikseleittäin suurennettuina.
- `tee_kuvakkeet.py`: tuottaa kaikki edellä mainitut.

## Suositus: D · Raahattava rivi

- Kuvaa sitä, mitä sovelluksessa oikeasti tehdään: rivejä taulukossa ja niiden järjestämistä.
  Se sopii myös nimeen *muokkaaja*.
- Burgundinen runko jatkaa BC Helsinki -ilmettä ja nykyistä kuvaketta, joten vaihdos ei
  tunnu brändimuutokselta.
- 16 px:n koossa D on luettavin: suurimmat yhtenäiset pinnat, kolme selvää riviä ja
  1 px:n sivuttaissiirto, joka näkyy.
- Asiakirja (E) ja nuoli (G) ovat yleisiä vientikuvakkeiden aiheita. D:n kultainen, sivuun
  siirtynyt rivi on omaleimaisempi.

Varavaihtoehto on **G**, jos halutaan vaalea kuvake, joka erottuu Dockin tummista
kuvakkeista. Sen nuoli on pienissä koissa kaikkein selvin.

## Tunnetut heikkoudet

- **16 px:n reunat:** Applen ruudukossa runko alkaa 1,56 px:n kohdalta, joten rungon
  reuna ja kulmat ovat 16 px:n koossa pehmeitä. Sisältö on silti terävää. Kun .ico/.icns
  tehdään, 16, 24 ja 32 px kannattaa piirtää suoraan vektorista niin, että runko on
  pikseleihin kohdistettu ja täyttää ruudun lähes kokonaan. Windows-kuvakkeet täyttävät
  pienissä koissa yleensä koko ruudun, joten tämä kasvattaa kuvaketta tehtäväpalkissa.
- **Tumma tehtäväpalkki:** burgundinen tai syvä burgundinen runko (D, E, F) erottuu
  #1E1E1E-taustasta heikosti. Tunnistettavuus nojaa vaaleisiin riveihin, jotka näkyvät hyvin.
- **F:** jaksosarakkeet näkyvät 16 px:n koossa raitoina ja tekevät kuvasta levottoman.
  Konsepti on myös kauimpana sovelluksen varsinaisesta tehtävästä.
- **G:** 0,5 yksikön reunarengas pehmenee 16 px:n koossa vaaleanpunertavaksi kehäksi.
- **E:** taitettu kulma häviää 16 px:n koossa, mutta arkin muoto erottuu silti.

.ico- ja .icns-tiedostot tehdään vasta, kun konsepti on valittu.
