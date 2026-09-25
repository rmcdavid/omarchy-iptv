# The guide at real provider scale (M2-09)

Owner: Product Owner. Status: v0.1, problem statement and scope. Governs the
next lane. This is a design problem, not a defect list: everything described
here behaves exactly as built.

## Why this exists

The live pass loaded a real subscriber's playlist and found the guide works
and is unpleasant at that size. I framed it at first as "a playlist with one
group", which is how it presented. Measuring real playlists shows that framing
was too narrow.

| Playlist | Channels | Groups | Largest group |
|---|---|---|---|
| Subscriber, US | 3,335 | 1 | 3,335 |
| Subscriber, sports | 1,833 | 2 | 1,000 |
| Public, US | 1,472 | 73 | 270 |
| Public, everything | 11,039 | 183 | 2,641 |

The public list is the well-grouped case and it still contains a group of
2,641 channels. So the real problem is not that a provider sometimes ships one
group. It is that THE GUIDE ASSUMES A GROUP IS A USEFUL NARROWING STEP, and a
group can be any size at all, including all of them.

A second measurement, from the same subscriber list: 2,217 of 3,335 channel
names begin with the same bracketed token, and hundreds more share one of two
other prefixes. Two thirds of the rows open with identical text. The row is
built to show a name, and the name's first third is the same on most rows.

## The three problems, stated plainly (not defects: a design brief's motivation)

1. **A group is not reliably a narrowing step.** When there is one group, the
   column is a fifth of the card doing nothing and duplicates the All entry.
   When a group holds 2,641 channels, choosing it narrows nothing. The column
   is excellent when groups are small and many, which is a real shape, but the
   design treats it as the primary navigation axis in every shape.
2. **There is no sense of position.** In a list of thousands nothing says
   where you are, how far in, or how much is left. Paging jumps land flush
   against the bottom edge with no indication that more exists.
3. **Rows waste their most valuable space.** A repeated provider prefix
   occupies the start of most rows, which is exactly where the eye lands when
   scanning, and it pushes the part that distinguishes one channel from
   another to the right.

## What must not change

Search is already good, and it is the thing that actually works at this scale.
The two-mode keyboard model stays. Nothing here may slow the guide's opening
or typing, which are budgeted and currently comfortable. The small-and-many
groups shape must not get worse in order to fix the large-group shape.

## Scope decision

Fix all three, in that order of value, in one lane. They are the same problem
seen from three angles: the guide was designed for a list you can hold in your
head, and real providers do not ship those.

Explicitly NOT in scope: a new navigation concept such as folders or
favourites-as-groups, any change to how playlists are parsed or cached, and
anything that requires a provider to format their data differently.

## The bar this must clear

An honest one, because the temptation here is to add cleverness. A change
earns its place only if it makes finding a channel in three thousand faster or
less irritating. Every addition costs screen space the channel list currently
uses, and a busier guide that looks more capable while being no faster to use
is a loss.

The subscriber's own playlist is the test case, with the 11,039-channel public
list as the scale case and the 73-group public list as the shape that must not
regress.
