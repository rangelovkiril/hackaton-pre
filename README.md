# Git Rescue Cheatsheet

---

## Комитнах в грешен бранч

```bash
git reset --soft HEAD~1 
git stash
git checkout correct-branch
git stash pop
git commit
```

## Искам да отменя последния комит (вече pushнат)

Вариант 1 — добавяш нов комит, който отменя промените:

```bash
git revert HEAD
```

Вариант 2 — махаш комита от историята изцяло:

```bash
git reset --soft HEAD~1
git push --force-with-lease
```

`--force-with-lease` е безопасната версия на `--force` — ако remote-ът се е променил откакто последно си fetch-нал, push-ът ще бъде отказан вместо да презапише чужда работа.

## Забравих файл в последния комит

```bash
git add forgotten-file.txt
git commit --amend --no-edit
```

Ако вече е pushнат: `git push --force-with-lease` (проверява дали някой друг не е pushнал междувременно).

## Merge conflict и не знам какво се случва

Винаги можеш да се върнеш на чисто:

```bash
git merge --abort
```

Ако искаш да го решиш — избери кой код остава, махни `<<<<<<<` маркерите, `git add`, `git commit`.

## Изтрих бранч, който ми трябва

```bash
git reflog    
git checkout -b restored-branch abc1234
```

Git пази обектите ~30 дни дори след "изтриване".

## Трябва да сменя бранча, но имам uncommitted промени

```bash
git stash
git checkout other-branch
git checkout -
git stash pop
```

## Комит съобщението ми е грешно

```bash
git commit --amend -m "правилното съобщение"
```

## Искам само един файл от друг бранч

```bash
git checkout other-branch -- path/to/file.txt
```

## Push rejected — remote е напред

Remote-ът има комити, които ти нямаш. Вместо merge commit:

```bash
git pull --rebase   
git push
```

## Remote е force push-нат и бранчът ми е diverged

Някой е пренаписал историята на remote-а. Локалният ти бранч вече не може нито да pull-не, нито да push-не.

```bash
git fetch origin
git reset --hard origin/branch-name    
```

> [!WARNING]
>
> `--hard` изтрива локални комити

Ако имаш локални комити, които искаш да запазиш:

```bash
git fetch origin
git rebase origin/branch-name
```

## Remote URL се е сменил (repo преместено/преименувано)

```bash
git remote get-url origin            
git remote set-url origin <new-url>   
```

## Stale remote бранчове (изтрити от колеги, но все още се виждат локално)

```bash
git fetch --prune
```

--- 

**Общ принцип:** Git почти никога не изтрива данни наистина. Дори `git reset --hard` може да се обърне чрез `git reflog`. Най-опасното нещо, което реално можеш да направиш, е `git push --force` в споделен бранч — всичко останало е reversible.
