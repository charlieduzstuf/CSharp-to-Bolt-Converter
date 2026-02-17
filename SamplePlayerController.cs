using UnityEngine;

public class PlayerController : MonoBehaviour
{
    public float speed = 5.0f;
    public int health = 100;
    private Vector3 movement;

    void Start()
    {
        Debug.Log("Player initialized!");
        health = 100;
    }

    void Update()
    {
        Debug.Log("Updating player...");

        if (health <= 0)
        {
            Debug.Log("Player died!");
        }
    }

    void OnTriggerEnter(Collider other)
    {
        Debug.Log("Trigger entered!");
    }
}
