declare module "urdf-loader" {
  import type { LoadingManager, Object3D } from "three";

  export type URDFJoint = Object3D & {
    setJointValue: (value: number) => void;
  };

  export type URDFRobot = Object3D & {
    joints: Record<string, URDFJoint>;
  };

  export default class URDFLoader {
    constructor(manager?: LoadingManager);
    loadAsync(path: string): Promise<URDFRobot>;
  }
}
