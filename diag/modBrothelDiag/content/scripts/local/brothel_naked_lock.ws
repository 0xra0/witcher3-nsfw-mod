// Keeps the scene partner nude for the whole brothel scene.
// A girl is locked once she is seen in her _naked look during a dialog or
// cutscene (the patched scene sets it at its start), so bystanders are never
// touched. While locked she is kept _naked and leftover clothing is hidden;
// when the scene ends she gets her _panties look and the clothing back.

@addField(CR4Player)
var brothelLocked : array<CActor>;

@addField(CR4Player)
var brothelLockReported : string;

// Fields default to false and are not saved, so the automatic free camera is off after every load until bautocam() turns it on.
@addField(CR4Player)
var brothelCamAutoEnabled : bool;

// Set when the lock (not the user) turned the free camera on.
@addField(CR4Player)
var brothelCamAutoOn : bool;

// The automatic free camera fires once per scene, so fcam() can turn it off.
@addField(CR4Player)
var brothelCamHandled : bool;

// The scene is lit for CDPR's original shots, so from the POV camera it is nearly
// black (mean 15/255 in the 19:06 video). Photo mode's exposure works outside
// photo mode; the old value is put back when the scene ends.
@addField(CR4Player)
var brothelExposureOn : bool;

@addField(CR4Player)
var brothelExposureOld : float;

function BrothelExposure(p : CR4Player, on : bool)
{
	var fx : CR4PhotomodeEffects;

	fx = theGame.GetPhotomodeEffects();
	if (!fx || p.brothelExposureOn == on)
		return;
	if (on)
	{
		p.brothelExposureOld = fx.GetExposure();
		fx.SetEnabled(true);
		fx.SetDofEnabled(false);
		fx.SetExposure(2.0);
		BDiag_Show("brothel exposure +2.0");
	}
	else
	{
		fx.SetExposure(p.brothelExposureOld);
		fx.SetEnabled(false);
	}
	p.brothelExposureOn = on;
}

@wrapMethod(CR4Player) function OnSpawned(spawnData : SEntitySpawnData)
{
	wrappedMethod(spawnData);
	AddTimer('BrothelNakedLockTimer', 0.2, true);
}

// Clothing some _naked looks still include: the garter (Passiflora 08,
// Beauclair 02) and the lingerie top (Peggy's prostitute_04).
// i_02_wa__novigrad_prostitute_clean is NOT hidden: it is her only lower legs
// (stockings); modBrothelNewScene swaps its mesh for bare legs. Their skin
// patches (i_02_wa__body_prostitute_body, ta0_01_wa__body) stay visible.
function BrothelShowClothes(actor : CActor, visible : bool)
{
	var names : array<string>;
	var component : CDrawableComponent;
	var i : int;

	names.PushBack("i_02_wa__novigrad_prostitute");
	names.PushBack("t_01_wa__lingerie");
	for (i = 0; i < names.Size(); i += 1)
	{
		component = (CDrawableComponent)actor.GetComponent(names[i]);
		if (component && component.IsVisible() != visible)
			component.SetVisible(visible);
	}
}

@addMethod(CR4Player)
timer function BrothelNakedLockTimer(dt : float, id : int)
{
	var actors : array<CActor>;
	var current, target : name;
	var i : int;

	if (!theGame.IsDialogOrCutscenePlaying())
	{
		for (i = 0; i < brothelLocked.Size(); i += 1)
		{
			if (!brothelLocked[i])
				continue;
			target = BDiag_Variant(brothelLocked[i].GetAppearance(), false);
			if (IsNameValid(target))
				brothelLocked[i].SetAppearance(target);
			BrothelShowClothes(brothelLocked[i], true);
		}
		brothelLocked.Clear();
		brothelLockReported = "";
		if (brothelCamAutoOn)
			BDiag_FreeCam(false);
		brothelCamAutoOn = false;
		brothelCamHandled = false;
		BrothelExposure(this, false);
		return;
	}

	actors = GetActorsInRange(this, 6.0, 20);
	for (i = 0; i < actors.Size(); i += 1)
	{
		current = actors[i].GetAppearance();
		if (actors[i] != this && StrEndsWith(NameToString(current), "_naked")
			&& IsNameValid(BDiag_Variant(current, true)) && !brothelLocked.Contains(actors[i]))
			brothelLocked.PushBack(actors[i]);
	}

	if (brothelLocked.Size() > 0)
		BrothelExposure(this, true);

	if (brothelLocked.Size() > 0 && !brothelCamHandled)
	{
		brothelCamHandled = true;
		if (brothelCamAutoEnabled && !theGame.IsFreeCameraEnabled())
		{
			BDiag_FreeCam(true);
			brothelCamAutoOn = true;
		}
	}

	for (i = 0; i < brothelLocked.Size(); i += 1)
	{
		if (!brothelLocked[i])
			continue;
		current = brothelLocked[i].GetAppearance();
		if (StrEndsWith(NameToString(current), "_panties"))
		{
			target = BDiag_Variant(current, true);
			brothelLocked[i].SetAppearance(target);
			if (brothelLockReported != NameToString(current))
				BDiag_Show("naked-lock: " + NameToString(current) + " -> " + NameToString(target));
			brothelLockReported = NameToString(current);
		}
		BrothelShowClothes(brothelLocked[i], false);
	}
}
