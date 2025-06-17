package list.community.controller;

import list.community.dto.DogdripPost;
import list.community.service.DogDripService;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

@RestController
@RequestMapping("/api/community")
public class DogdripController {

    private final DogDripService dogdripService = new DogDripService();


    @GetMapping("/dogdrip")
    public List<DogdripPost> getPopularPosts() {
        return dogdripService.getPopularPosts();
    }
}
