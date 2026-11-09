// Test player for brothel cutscenes made in Blender. Console only:
//   bnew()  - play the new scene with the nearest brothel girl, placed at
//             Geralt's position and facing. Stand at the foot of the bed.
// The scene is a row in gameplay\globals\cutscene.csv shipped in this mod's
// bundle. Needs modBrothelDiag (partner search, naked lock).

exec function bnew()
{
	var girl : CActor;
	var naked : name;
	var names : array<string>;
	var entities : array<CEntity>;

	if (theGame.IsCurrentlyPlayingNonGameplayScene())
	{
		BDiag_Show("bnew: another scene is playing");
		return;
	}
	girl = BDiag_CamPartner();
	if (!girl)
	{
		BDiag_Show("bnew: no brothel girl within 12 m");
		return;
	}
	// The naked lock keeps this look for the whole cutscene.
	naked = BDiag_Variant(girl.GetAppearance(), true);
	if (IsNameValid(naked))
		girl.SetAppearance(naked);

	// Role names are the actor names inside the .w2cutscene.
	names.PushBack("geralt");
	entities.PushBack(thePlayer);
	names.PushBack("prostitute");
	entities.PushBack(girl);

	if (theGame.PlayCutsceneAsync("BRN_sex_do_component_rt", names, entities,
		thePlayer.GetWorldPosition(), thePlayer.GetWorldRotation()))
		BDiag_Show("bnew: playing with " + NameToString(girl.GetAppearance()));
	else
		BDiag_Show("bnew: the engine rejected the cutscene");
}
