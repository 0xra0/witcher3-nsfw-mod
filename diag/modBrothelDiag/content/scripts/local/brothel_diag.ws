// Brothel appearance diagnostic. Console only; does nothing unless called.
//   bdiag()   - list nearby NPCs: current appearance and tags
//   bnaked()  - force each nearby brothel girl's _naked appearance
//   bpanties()- force each nearby brothel girl's _panties appearance
//   fcam()    - toggle the free camera; bshot() screenshot; bcampos() camera
//   borbit(deg) bzoom(m) bup(m) bfocus() - move the free camera around her
//   bautocam()- toggle the free camera turning on when a brothel scene starts

function BDiag_Nearby() : array<CActor>
{
	var found, result : array<CActor>;
	var i : int;

	found = GetActorsInRange(thePlayer, 12.0, 30);
	for (i = 0; i < found.Size(); i += 1)
	{
		if (found[i] != thePlayer)
			result.PushBack(found[i]);
	}
	return result;
}

function BDiag_Show(text : string)
{
	theGame.GetGuiManager().ShowNotification(text, 15000.0, true);
	LogChannel('BrothelDiag', text);
}

// Maps any of a brothel girl's three looks to the requested variant.
function BDiag_Variant(current : name, naked : bool) : name
{
	var base : string;

	base = NameToString(current);
	base = StrReplace(base, "_naked", "");
	base = StrReplace(base, "_panties", "");
	switch (base)
	{
		case "courtesan_07": if (naked) return 'courtesan_07_naked'; return 'courtesan_07_panties';
		case "courtesan_08": if (naked) return 'courtesan_08_naked'; return 'courtesan_08_panties';
		case "__passiflora_elven_prostitute": if (naked) return '__passiflora_elven_prostitute_naked'; return '__passiflora_elven_prostitute_panties';
		case "prostitute_01": if (naked) return 'prostitute_01_naked'; return 'prostitute_01_panties';
		case "prostitute_02": if (naked) return 'prostitute_02_naked'; return 'prostitute_02_panties';
		case "prostitute_03": if (naked) return 'prostitute_03_naked'; return 'prostitute_03_panties';
		case "prostitute_04": if (naked) return 'prostitute_04_naked'; return 'prostitute_04_panties';
		case "prostitute_05": if (naked) return 'prostitute_05_naked'; return 'prostitute_05_panties';
		case "prostitute_06": if (naked) return 'prostitute_06_naked'; return 'prostitute_06_panties';
		case "__lw_city_brothel_prostitute_01": if (naked) return '__lw_city_brothel_prostitute_01_naked'; return '__lw_city_brothel_prostitute_01_panties';
		case "__lw_city_brothel_prostitute_02": if (naked) return '__lw_city_brothel_prostitute_02_naked'; return '__lw_city_brothel_prostitute_02_panties';
		case "__lw_city_brothel_prostitute_03": if (naked) return '__lw_city_brothel_prostitute_03_naked'; return '__lw_city_brothel_prostitute_03_panties';
	}
	return '';
}

exec function bdiag()
{
	var actors : array<CActor>;
	var tags : array<name>;
	var text : string;
	var i, j : int;

	actors = BDiag_Nearby();
	if (actors.Size() == 0)
		BDiag_Show("bdiag: no NPCs within 12 m");
	for (i = 0; i < actors.Size(); i += 1)
	{
		tags = actors[i].GetTags();
		text = actors[i].ToString() + " app=" + NameToString(actors[i].GetAppearance()) + " tags=";
		for (j = 0; j < tags.Size(); j += 1)
			text += NameToString(tags[j]) + " ";
		BDiag_Show(text);
	}
}

function BDiag_Apply(naked : bool)
{
	var actors : array<CActor>;
	var target : name;
	var i, n : int;

	actors = BDiag_Nearby();
	for (i = 0; i < actors.Size(); i += 1)
	{
		target = BDiag_Variant(actors[i].GetAppearance(), naked);
		if (IsNameValid(target))
		{
			actors[i].SetAppearance(target);
			BDiag_Show("set " + NameToString(target) + " -> now " + NameToString(actors[i].GetAppearance()));
			n += 1;
		}
	}
	if (n == 0)
		BDiag_Show("no brothel girl within 12 m");
}

exec function bnaked()
{
	BDiag_Apply(true);
}

exec function bpanties()
{
	BDiag_Apply(false);
}

// Orbit state for the free camera: it circles the scene partner, so it always
// looks at her even when the scene keeps the keyboard from moving it.
@addField(CR4Player)
var brothelCamTarget : CActor;

@addField(CR4Player)
var brothelCamYaw : float;

@addField(CR4Player)
var brothelCamDist : float;

@addField(CR4Player)
var brothelCamUp : float;

// The partner: a locked girl in a scene, else the nearest brothel girl.
function BDiag_CamPartner() : CActor
{
	var actors : array<CActor>;
	var i : int;

	for (i = 0; i < thePlayer.brothelLocked.Size(); i += 1)
	{
		if (thePlayer.brothelLocked[i])
			return thePlayer.brothelLocked[i];
	}
	actors = BDiag_Nearby();
	for (i = 0; i < actors.Size(); i += 1)
	{
		if (IsNameValid(BDiag_Variant(actors[i].GetAppearance(), true)))
			return actors[i];
	}
	return NULL;
}

// Puts the free camera on its orbit, aimed at the partner's chest.
function BDiag_CamApply()
{
	var player : CR4Player;
	var target, eye : Vector;

	player = thePlayer;
	if (!player.brothelCamTarget || !theGame.IsFreeCameraEnabled())
		return;
	target = player.brothelCamTarget.GetWorldPosition() + Vector(0, 0, 0.9);
	eye = target + VecFromHeading(player.brothelCamYaw) * player.brothelCamDist
		+ Vector(0, 0, player.brothelCamUp);
	theGame.MoveFreeCamera(eye, VecToRotation(target - eye));
}

// Free camera (keys in bin/config/base/freecamera.ini: WASD move, Q/E up/down,
// Shift faster, P screenshot). Scenes may swallow those keys, so borbit/bzoom/
// bup move it from the console instead.
function BDiag_FreeCam(on : bool)
{
	var player : CR4Player;

	if (theGame.IsFreeCameraEnabled() == on)
		return;
	theGame.EnableFreeCamera(on);
	if (!on)
	{
		BDiag_Show("free camera: off");
		return;
	}
	player = thePlayer;
	player.brothelCamTarget = BDiag_CamPartner();
	if (!player.brothelCamTarget)
	{
		theGame.MoveFreeCamera(theCamera.GetCameraPosition(), theCamera.GetCameraRotation());
		BDiag_Show("free camera: on, no partner nearby (WASD, Q/E, Shift)");
		return;
	}
	// Start on the side the scene camera was on.
	player.brothelCamYaw = VecHeading(theCamera.GetCameraPosition()
		- player.brothelCamTarget.GetWorldPosition());
	player.brothelCamDist = 2.5;
	player.brothelCamUp = 0.4;
	BDiag_CamApply();
	BDiag_Show("free camera: on - borbit(45) bzoom(-0.5) bup(0.3) bfocus()");
}

exec function borbit(degrees : float)
{
	var player : CR4Player;

	player = thePlayer;
	player.brothelCamYaw += degrees;
	BDiag_CamApply();
}

exec function bzoom(meters : float)
{
	var player : CR4Player;

	player = thePlayer;
	player.brothelCamDist = MaxF(0.5, player.brothelCamDist + meters);
	BDiag_CamApply();
}

exec function bup(meters : float)
{
	var player : CR4Player;

	player = thePlayer;
	player.brothelCamUp += meters;
	BDiag_CamApply();
}

// Re-aims at the partner after WASD moved the camera away, or picks her again.
exec function bfocus()
{
	var player : CR4Player;

	player = thePlayer;
	if (!theGame.IsFreeCameraEnabled())
	{
		BDiag_FreeCam(true);
		return;
	}
	player.brothelCamTarget = BDiag_CamPartner();
	if (!player.brothelCamTarget)
		BDiag_Show("bfocus: no brothel girl nearby");
	BDiag_CamApply();
}

function BDiag_CamText() : string
{
	var pos : Vector;
	var rot : EulerAngles;

	pos = theCamera.GetCameraPosition();
	rot = theCamera.GetCameraRotation();
	return "pos=" + VecToString(pos) + " pitch=" + FloatToString(rot.Pitch)
		+ " yaw=" + FloatToString(rot.Yaw) + " roll=" + FloatToString(rot.Roll)
		+ " fov=" + FloatToString(theCamera.GetFov());
}

// thePlayer is const, so fields are written through a local handle.
exec function fcam()
{
	var player : CR4Player;

	player = thePlayer;
	player.brothelCamAutoOn = false;
	BDiag_FreeCam(!theGame.IsFreeCameraEnabled());
}

// Screenshot (same path as photo mode) plus the camera it was taken from.
exec function bshot()
{
	theGame.TakeScreenshot();
	BDiag_Show("screenshot: " + BDiag_CamText());
}

exec function bcampos()
{
	BDiag_Show("camera: " + BDiag_CamText());
}

// Switches the automatic free camera at brothel scene start on or off.
exec function bautocam()
{
	var player : CR4Player;

	player = thePlayer;
	player.brothelCamAutoEnabled = !player.brothelCamAutoEnabled;
	if (!player.brothelCamAutoEnabled)
		BDiag_Show("auto free camera: off");
	else
		BDiag_Show("auto free camera: on");
}
