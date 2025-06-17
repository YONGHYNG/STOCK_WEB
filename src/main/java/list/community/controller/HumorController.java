package list.community.controller;

import list.community.dto.HumorPost;
import list.community.service.HumorService;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

@RestController
@RequestMapping("/api/community")
public class HumorController {

    private final HumorService humorService = new HumorService();

    @GetMapping("/humor/best")
    public List<HumorPost> getBestHumorPosts(){
        return humorService.getBestHumorPosts();
    }

    @GetMapping("/humor/bestofbest")
    public List<HumorPost> getBestOfBestHumorPosts() {
        return humorService.getBestOfBestHumorPosts();
    }
}

